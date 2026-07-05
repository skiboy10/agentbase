"""
Ollama embedding provider implementation.
"""
import asyncio
from typing import Optional
import httpx
import structlog

from app.providers.embedding_base import EmbeddingProvider
from app.providers.base import EmbeddingModelInfo, EmbeddingResponse
from app.core.config import get_settings

logger = structlog.get_logger()

# Known Ollama embedding models with their dimensions
OLLAMA_EMBEDDING_MODELS = {
    "nomic-embed-text": {"dimensions": 768, "max_tokens": 8192},
    "mxbai-embed-large": {"dimensions": 1024, "max_tokens": 512},
    "all-minilm": {"dimensions": 384, "max_tokens": 512},
    "snowflake-arctic-embed": {"dimensions": 1024, "max_tokens": 512},
    "qwen3-embedding": {"dimensions": 2560, "max_tokens": 8192},
}


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider for local models."""

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self._client = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        return self._client

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def is_configured(self) -> bool:
        return True  # Ollama doesn't need API key

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazy init of instance-level semaphore (must be created in event loop)."""
        if self._semaphore is None:
            settings = get_settings()
            self._semaphore = asyncio.Semaphore(settings.embedding_concurrency)
        return self._semaphore

    async def embed(
        self,
        texts: list[str],
        model: str,
        input_type: str = "document",
    ) -> EmbeddingResponse:
        """Generate embeddings using Ollama's batch /api/embed endpoint.

        Uses an instance-level semaphore so concurrent indexing jobs don't
        overwhelm Ollama. Set EMBEDDING_CONCURRENCY to match your Ollama
        instance's OLLAMA_NUM_PARALLEL for best throughput.
        """
        if not texts:
            return EmbeddingResponse(
                embeddings=[], model=model, provider=self.name,
                total_tokens=None, dimensions=0,
            )

        client = self._get_client()
        semaphore = self._get_semaphore()

        async with semaphore:
            try:
                response = await client.post(
                    "/api/embed",
                    json={"model": model, "input": texts},
                )
                response.raise_for_status()
                data = response.json()
                embeddings = data["embeddings"]
            except httpx.HTTPError as e:
                logger.error("Ollama embedding error", error=str(e), model=model)
                raise

        dimensions = len(embeddings[0]) if embeddings else 0

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model,
            provider=self.name,
            total_tokens=data.get("prompt_eval_count"),
            dimensions=dimensions,
        )

    async def list_embedding_models(self) -> list[EmbeddingModelInfo]:
        """List available Ollama embedding models."""
        client = self._get_client()

        # Try to get models from Ollama, filter for embedding-capable ones
        try:
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("models", []):
                model_name = model_data["name"]
                # Check if it's a known embedding model
                base_name = model_name.split(":")[0]
                if base_name in OLLAMA_EMBEDDING_MODELS:
                    info = OLLAMA_EMBEDDING_MODELS[base_name]
                    models.append(EmbeddingModelInfo(
                        id=model_name,
                        name=model_name,
                        provider=self.name,
                        dimensions=info["dimensions"],
                        max_input_tokens=info["max_tokens"],
                    ))
            return models
        except httpx.HTTPError:
            # Return known models as fallback (not pulled yet)
            return [
                EmbeddingModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=self.name,
                    dimensions=info["dimensions"],
                    max_input_tokens=info["max_tokens"],
                )
                for model_id, info in OLLAMA_EMBEDDING_MODELS.items()
            ]

    def get_model_dimensions(self, model: str) -> int:
        """Get dimensions for an Ollama embedding model."""
        base_name = model.split(":")[0]
        if base_name in OLLAMA_EMBEDDING_MODELS:
            return OLLAMA_EMBEDDING_MODELS[base_name]["dimensions"]
        return 768  # Default fallback

    async def health_check(self) -> bool:
        """Check if Ollama is accessible for embeddings."""
        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Ollama embedding health check failed", error=str(e))
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
