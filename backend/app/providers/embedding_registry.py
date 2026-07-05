"""
Embedding provider registry for managing embedding providers.
"""
from typing import Optional
import structlog

from app.providers.embedding_base import EmbeddingProvider
from app.providers.embedding_openai import OpenAIEmbeddingProvider
from app.providers.embedding_ollama import OllamaEmbeddingProvider
from app.providers.embedding_cohere import CohereEmbeddingProvider
from app.providers.embedding_voyage import VoyageEmbeddingProvider
from app.providers.base import EmbeddingModelInfo, EmbeddingResponse
from app.core.config import get_settings

logger = structlog.get_logger()


class EmbeddingRegistry:
    """
    Registry for managing embedding providers.
    """

    def __init__(self):
        self._providers: dict[str, EmbeddingProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize embedding providers."""
        settings = get_settings()

        # Always add Ollama (no API key required)
        self._providers["ollama"] = OllamaEmbeddingProvider()

        # Add OpenAI if configured
        if settings.openai_api_key:
            self._providers["openai"] = OpenAIEmbeddingProvider()

        # Add Cohere if configured
        if settings.cohere_api_key:
            self._providers["cohere"] = CohereEmbeddingProvider()

        # Add Voyage AI if configured
        if settings.voyage_api_key:
            self._providers["voyage"] = VoyageEmbeddingProvider()

        logger.info(
            "Embedding providers initialized",
            available=list(self._providers.keys()),
        )

    def configure_provider(self, name: str, api_key: str) -> None:
        """Configure an embedding provider with an API key (e.g., from DB).

        Called during startup to load DB-stored provider configs into the
        embedding registry, matching how the LLM registry loads from DB.
        """
        if name == "openai" and "openai" not in self._providers:
            self._providers["openai"] = OpenAIEmbeddingProvider(api_key=api_key)
            logger.info("Embedding provider configured from DB", provider="openai")
        elif name == "cohere" and "cohere" not in self._providers:
            self._providers["cohere"] = CohereEmbeddingProvider(api_key=api_key)
            logger.info("Embedding provider configured from DB", provider="cohere")
        elif name == "voyage" and "voyage" not in self._providers:
            self._providers["voyage"] = VoyageEmbeddingProvider(api_key=api_key)
            logger.info("Embedding provider configured from DB", provider="voyage")

    def get_provider(self, name: str) -> Optional[EmbeddingProvider]:
        """Get an embedding provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        """List all registered embedding providers."""
        return list(self._providers.keys())

    def list_configured_providers(self) -> list[str]:
        """List embedding providers that are properly configured."""
        return [
            name for name, provider in self._providers.items()
            if provider.is_configured
        ]

    async def list_all_embedding_models(self) -> list[EmbeddingModelInfo]:
        """List all embedding models from all configured providers."""
        all_models = []
        for provider in self._providers.values():
            if provider.is_configured:
                try:
                    models = await provider.list_embedding_models()
                    all_models.extend(models)
                except Exception as e:
                    logger.warning(
                        "Failed to list embedding models from provider",
                        provider=provider.name,
                        error=str(e),
                    )
        return all_models

    async def embed(
        self,
        provider_name: str,
        model: str,
        texts: list[str],
        input_type: str = "document",
    ) -> EmbeddingResponse:
        """
        Generate embeddings using a specific provider.

        Args:
            input_type: "document" for indexing, "query" for search queries.
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Embedding provider '{provider_name}' not found")

        if not provider.is_configured:
            raise ValueError(f"Embedding provider '{provider_name}' is not configured")

        return await provider.embed(texts=texts, model=model, input_type=input_type)

    def get_model_dimensions(self, provider_name: str, model: str) -> int:
        """Get the dimensions for a specific model."""
        provider = self.get_provider(provider_name)
        if provider:
            return provider.get_model_dimensions(model)
        return 1536  # Default fallback

    def get_default_embedding_config(self) -> tuple[str, str, int]:
        """
        Get the default embedding provider, model, and dimensions.

        Returns:
            Tuple of (provider_name, model_name, dimensions)
        """
        settings = get_settings()
        provider_name = settings.embedding_provider
        model = settings.embedding_model

        provider = self.get_provider(provider_name)
        if provider:
            dimensions = provider.get_model_dimensions(model)
        else:
            dimensions = 1536

        return provider_name, model, dimensions


# Global registry instance
_embedding_registry: Optional[EmbeddingRegistry] = None


def get_embedding_registry() -> EmbeddingRegistry:
    """Get the global embedding registry instance."""
    global _embedding_registry
    if _embedding_registry is None:
        _embedding_registry = EmbeddingRegistry()
    return _embedding_registry
