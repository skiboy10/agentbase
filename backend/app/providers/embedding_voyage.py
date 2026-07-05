"""
Voyage AI embedding provider implementation.

Supports voyage-3-large, voyage-3, voyage-3-lite, and voyage-code-3 models.
Voyage requires specifying input_type: "document" for indexing,
"query" for search queries.
"""
import asyncio
from typing import Optional
import structlog

from app.providers.embedding_base import EmbeddingProvider
from app.providers.base import EmbeddingModelInfo, EmbeddingResponse
from app.core.config import get_settings

logger = structlog.get_logger()

# Voyage AI embedding models with their dimensions
VOYAGE_EMBEDDING_MODELS = {
    "voyage-3-large": {"dimensions": 1024, "max_tokens": 32000},
    "voyage-3": {"dimensions": 1024, "max_tokens": 32000},
    "voyage-3-lite": {"dimensions": 512, "max_tokens": 32000},
    "voyage-code-3": {"dimensions": 1024, "max_tokens": 32000},
}


class VoyageEmbeddingProvider(EmbeddingProvider):
    """Voyage AI embedding provider."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.voyage_api_key
        self._client = None

    def _get_client(self):
        """Lazy initialization of Voyage client."""
        if self._client is None:
            import voyageai
            self._client = voyageai.Client(api_key=self.api_key)
        return self._client

    @property
    def name(self) -> str:
        return "voyage"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def embed(
        self,
        texts: list[str],
        model: str,
        input_type: str = "document",
    ) -> EmbeddingResponse:
        """Generate embeddings using Voyage AI."""
        if not self.is_configured:
            raise ValueError("Voyage API key not configured")
        if not texts:
            return EmbeddingResponse(embeddings=[], model=model, provider=self.name, dimensions=0)

        client = self._get_client()
        # Voyage uses "document" and "query" directly
        voyage_input_type = input_type if input_type in ("document", "query") else "document"

        try:
            # Voyage SDK is synchronous — run in executor for async compatibility
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: client.embed(texts, model=model, input_type=voyage_input_type),
            )

            embeddings = result.embeddings
            dimensions = len(embeddings[0]) if embeddings else 0

            return EmbeddingResponse(
                embeddings=embeddings,
                model=model,
                provider=self.name,
                total_tokens=getattr(result, 'total_tokens', None),
                dimensions=dimensions,
            )
        except Exception as e:
            logger.error("Voyage embedding error", error=str(e), model=model)
            raise

    async def list_embedding_models(self) -> list[EmbeddingModelInfo]:
        """List available Voyage AI embedding models."""
        return [
            EmbeddingModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                dimensions=info["dimensions"],
                max_input_tokens=info["max_tokens"],
            )
            for model_id, info in VOYAGE_EMBEDDING_MODELS.items()
        ]

    def get_model_dimensions(self, model: str) -> int:
        """Get dimensions for a Voyage AI embedding model."""
        if model in VOYAGE_EMBEDDING_MODELS:
            return VOYAGE_EMBEDDING_MODELS[model]["dimensions"]
        return 1024  # Default for Voyage models

    async def health_check(self) -> bool:
        """Check if Voyage AI embeddings are accessible."""
        if not self.is_configured:
            return False
        try:
            await self.embed(["test"], "voyage-3-lite")
            return True
        except Exception as e:
            logger.warning("Voyage embedding health check failed", error=str(e))
            return False
