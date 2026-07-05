"""
Cohere embedding provider implementation.

Supports embed-v4 (configurable dimensions) and embed-v3 models.
Cohere requires specifying input_type: "search_document" for indexing,
"search_query" for search queries.
"""
from typing import Optional
import structlog

from app.providers.embedding_base import EmbeddingProvider
from app.providers.base import EmbeddingModelInfo, EmbeddingResponse
from app.core.config import get_settings

logger = structlog.get_logger()

# Cohere embedding models with their default dimensions
COHERE_EMBEDDING_MODELS = {
    "embed-v4": {"dimensions": 1536, "max_tokens": 128000},
    "embed-english-v3.0": {"dimensions": 1024, "max_tokens": 512},
    "embed-multilingual-v3.0": {"dimensions": 1024, "max_tokens": 512},
    "embed-english-light-v3.0": {"dimensions": 384, "max_tokens": 512},
    "embed-multilingual-light-v3.0": {"dimensions": 384, "max_tokens": 512},
}

# Map generic input_type to Cohere-specific values
_COHERE_INPUT_TYPES = {
    "document": "search_document",
    "query": "search_query",
}


class CohereEmbeddingProvider(EmbeddingProvider):
    """Cohere embedding provider using the v2 API."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.cohere_api_key
        self._client = None

    def _get_client(self):
        """Lazy initialization of Cohere async client."""
        if self._client is None:
            import cohere
            self._client = cohere.AsyncClient(api_key=self.api_key)
        return self._client

    @property
    def name(self) -> str:
        return "cohere"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def embed(
        self,
        texts: list[str],
        model: str,
        input_type: str = "document",
    ) -> EmbeddingResponse:
        """Generate embeddings using Cohere v2 API."""
        if not self.is_configured:
            raise ValueError("Cohere API key not configured")
        if not texts:
            return EmbeddingResponse(embeddings=[], model=model, provider=self.name, dimensions=0)

        client = self._get_client()
        cohere_input_type = _COHERE_INPUT_TYPES.get(input_type, "search_document")

        try:
            response = await client.v2.embed(
                model=model,
                texts=texts,
                input_type=cohere_input_type,
                embedding_types=["float"],
            )

            embeddings = response.embeddings.float_
            dimensions = len(embeddings[0]) if embeddings else 0

            return EmbeddingResponse(
                embeddings=embeddings,
                model=model,
                provider=self.name,
                total_tokens=response.meta.billed_units.input_tokens if response.meta and response.meta.billed_units else None,
                dimensions=dimensions,
            )
        except Exception as e:
            logger.error("Cohere embedding error", error=str(e), model=model)
            raise

    async def list_embedding_models(self) -> list[EmbeddingModelInfo]:
        """List available Cohere embedding models."""
        return [
            EmbeddingModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                dimensions=info["dimensions"],
                max_input_tokens=info["max_tokens"],
            )
            for model_id, info in COHERE_EMBEDDING_MODELS.items()
        ]

    def get_model_dimensions(self, model: str) -> int:
        """Get dimensions for a Cohere embedding model."""
        if model in COHERE_EMBEDDING_MODELS:
            return COHERE_EMBEDDING_MODELS[model]["dimensions"]
        return 1024  # Default for Cohere v3 models

    async def health_check(self) -> bool:
        """Check if Cohere embeddings are accessible."""
        if not self.is_configured:
            return False
        try:
            await self.embed(["test"], "embed-english-v3.0")
            return True
        except Exception as e:
            logger.warning("Cohere embedding health check failed", error=str(e))
            return False
