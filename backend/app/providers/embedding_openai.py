"""
OpenAI embedding provider implementation.
"""
from typing import Optional
import structlog

from app.providers.embedding_base import EmbeddingProvider
from app.providers.base import EmbeddingModelInfo, EmbeddingResponse
from app.core.config import get_settings

logger = structlog.get_logger()

# OpenAI embedding models with their dimensions
OPENAI_EMBEDDING_MODELS = {
    "text-embedding-3-small": {"dimensions": 1536, "max_tokens": 8191},
    "text-embedding-3-large": {"dimensions": 3072, "max_tokens": 8191},
    "text-embedding-ada-002": {"dimensions": 1536, "max_tokens": 8191},
}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    @property
    def name(self) -> str:
        return "openai"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def embed(
        self,
        texts: list[str],
        model: str,
        input_type: str = "document",
    ) -> EmbeddingResponse:
        """Generate embeddings using OpenAI."""
        if not self.is_configured:
            raise ValueError("OpenAI API key not configured")

        client = self._get_client()

        try:
            response = await client.embeddings.create(
                model=model,
                input=texts,
            )

            embeddings = [item.embedding for item in response.data]
            dimensions = len(embeddings[0]) if embeddings else 0

            return EmbeddingResponse(
                embeddings=embeddings,
                model=model,
                provider=self.name,
                total_tokens=response.usage.total_tokens if response.usage else None,
                dimensions=dimensions,
            )
        except Exception as e:
            logger.error("OpenAI embedding error", error=str(e), model=model)
            raise

    async def list_embedding_models(self) -> list[EmbeddingModelInfo]:
        """List available OpenAI embedding models."""
        return [
            EmbeddingModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                dimensions=info["dimensions"],
                max_input_tokens=info["max_tokens"],
            )
            for model_id, info in OPENAI_EMBEDDING_MODELS.items()
        ]

    def get_model_dimensions(self, model: str) -> int:
        """Get dimensions for an OpenAI embedding model."""
        if model in OPENAI_EMBEDDING_MODELS:
            return OPENAI_EMBEDDING_MODELS[model]["dimensions"]
        return 1536  # Default fallback

    async def health_check(self) -> bool:
        """Check if OpenAI embeddings are accessible."""
        if not self.is_configured:
            return False
        try:
            await self.embed(["test"], "text-embedding-3-small")
            return True
        except Exception as e:
            logger.warning("OpenAI embedding health check failed", error=str(e))
            return False
