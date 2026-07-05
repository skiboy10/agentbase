"""
Provider registry for managing LLM provider instances.
"""
from typing import Optional
import structlog

from app.providers.base import LLMProvider, ChatMessage, ChatResponse, ModelInfo
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.grok import GrokProvider
from app.providers.google import GoogleProvider
from app.core.config import get_settings

logger = structlog.get_logger()

# Map provider names to their classes
PROVIDER_CLASSES = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "grok": GrokProvider,
    "google": GoogleProvider,
}


class ProviderRegistry:
    """
    Registry for managing LLM providers.

    Provides a unified interface to route requests to the appropriate provider
    based on configuration.
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize all configured providers from environment variables."""
        settings = get_settings()

        # Always add Ollama (doesn't need API key)
        self._providers["ollama"] = OllamaProvider()

        # Add cloud providers if configured via environment
        if settings.openai_api_key:
            self._providers["openai"] = OpenAIProvider()

        if settings.anthropic_api_key:
            self._providers["anthropic"] = AnthropicProvider()

        if settings.grok_api_key:
            self._providers["grok"] = GrokProvider()

        if settings.google_api_key:
            self._providers["google"] = GoogleProvider()

        logger.info(
            "Providers initialized",
            available=list(self._providers.keys()),
        )

    def configure_provider(
        self,
        provider_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bool:
        """
        Configure or reconfigure a provider with new credentials.

        This allows providers to be configured at runtime from database-stored
        API keys, not just environment variables.

        Args:
            provider_name: Name of the provider to configure
            api_key: API key for the provider
            base_url: Optional base URL override

        Returns:
            True if provider was successfully configured
        """
        if provider_name not in PROVIDER_CLASSES:
            logger.warning("Unknown provider", provider=provider_name)
            return False

        provider_class = PROVIDER_CLASSES[provider_name]

        try:
            # Create new provider instance with provided credentials
            if provider_name == "ollama":
                # Ollama uses base_url, not api_key
                self._providers[provider_name] = provider_class(base_url=base_url)
            else:
                # Cloud providers use api_key
                kwargs = {}
                if api_key:
                    kwargs["api_key"] = api_key
                if base_url:
                    kwargs["base_url"] = base_url
                self._providers[provider_name] = provider_class(**kwargs)

            logger.info(
                "Provider configured",
                provider=provider_name,
                is_configured=self._providers[provider_name].is_configured,
            )
            return True
        except Exception as e:
            logger.error("Failed to configure provider", provider=provider_name, error=str(e))
            return False

    def remove_provider(self, provider_name: str) -> bool:
        """
        Remove a provider from the registry.

        Args:
            provider_name: Name of the provider to remove

        Returns:
            True if provider was removed
        """
        if provider_name in self._providers and provider_name != "ollama":
            del self._providers[provider_name]
            logger.info("Provider removed", provider=provider_name)
            return True
        return False

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        """List all registered providers."""
        return list(self._providers.keys())

    def list_configured_providers(self) -> list[str]:
        """List providers that are properly configured."""
        return [
            name for name, provider in self._providers.items()
            if provider.is_configured
        ]

    async def list_all_models(self) -> list[ModelInfo]:
        """List all models from all configured providers."""
        all_models = []
        for provider in self._providers.values():
            if provider.is_configured:
                try:
                    models = await provider.list_models()
                    all_models.extend(models)
                except Exception as e:
                    logger.warning(
                        "Failed to list models from provider",
                        provider=provider.name,
                        error=str(e),
                    )
        return all_models

    async def chat(
        self,
        provider_name: str,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """
        Send a chat request to a specific provider.

        Args:
            provider_name: Name of the provider to use
            model: Model identifier
            messages: List of chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            system_prompt: Optional system prompt

        Returns:
            ChatResponse from the provider
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider '{provider_name}' not found")

        if not provider.is_configured:
            raise ValueError(f"Provider '{provider_name}' is not configured")

        return await provider.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all providers."""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.health_check()
        return results

    def get_default_provider_for_task(self, task_type: str) -> tuple[str, str]:
        """
        Get the default provider and model for a task type.

        Args:
            task_type: Currently only ``"knowledge"`` is supported.

        Returns:
            Tuple of (provider_name, model_name)

        Raises:
            ValueError: If task_type is not ``"knowledge"``.
        """
        settings = get_settings()

        if task_type == "knowledge":
            return settings.default_knowledge_provider, settings.default_knowledge_model
        raise ValueError(f"Unknown task type: {task_type}")


# Global registry instance
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Get the global provider registry instance."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
