"""
Abstract base class for embedding providers.
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.providers.base import EmbeddingModelInfo, EmbeddingResponse


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.

    Providers that support embeddings should implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai', 'ollama')."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider is properly configured."""
        pass

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        model: str,
        input_type: str = "document",
    ) -> EmbeddingResponse:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            model: Model identifier to use
            input_type: "document" for indexing, "query" for search queries.
                       Providers that distinguish (Cohere, Voyage) use this
                       to optimize embeddings. Others ignore it.

        Returns:
            EmbeddingResponse with embeddings and metadata
        """
        pass

    @abstractmethod
    async def list_embedding_models(self) -> list[EmbeddingModelInfo]:
        """
        List available embedding models from this provider.

        Returns:
            List of available embedding model information
        """
        pass

    @abstractmethod
    def get_model_dimensions(self, model: str) -> int:
        """
        Get the embedding dimensions for a specific model.

        Args:
            model: Model identifier

        Returns:
            Number of dimensions in the embedding vector
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the embedding provider is accessible.

        Returns:
            True if provider is healthy, False otherwise
        """
        return self.is_configured
