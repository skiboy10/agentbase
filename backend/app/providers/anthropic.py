"""
Anthropic (Claude) provider implementation.
"""
from typing import AsyncGenerator, Optional
import structlog

from app.providers.base import (
    LLMProvider,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
)
from app.core.config import get_settings

logger = structlog.get_logger()

# Known Anthropic models and their context windows
ANTHROPIC_MODELS = {
    "claude-opus-4-20250514": {"context": 200000, "capabilities": ["coding", "reasoning", "vision"]},
    "claude-sonnet-4-20250514": {"context": 200000, "capabilities": ["coding", "reasoning", "vision"]},
    "claude-3-5-sonnet-20241022": {"context": 200000, "capabilities": ["coding", "reasoning", "vision"]},
    "claude-3-5-haiku-20241022": {"context": 200000, "capabilities": ["coding", "reasoning"]},
    "claude-3-opus-20240229": {"context": 200000, "capabilities": ["coding", "reasoning", "vision"]},
    "claude-3-sonnet-20240229": {"context": 200000, "capabilities": ["coding", "reasoning", "vision"]},
    "claude-3-haiku-20240307": {"context": 200000, "capabilities": ["coding", "reasoning"]},
}


class AnthropicProvider(LLMProvider):
    """
    Anthropic API provider for Claude models.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self._client = None

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Send chat request to Anthropic."""
        if not self.is_configured:
            raise ValueError("Anthropic API key not configured")

        client = self._get_client()

        # Anthropic uses a different message format
        formatted_messages = []
        for msg in messages:
            # Skip system messages - they go in the system parameter
            if msg.role.value != "system":
                formatted_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens or 4096,
                system=system_prompt or "",
                messages=formatted_messages,
                temperature=temperature,
            )

            # Extract text from content blocks
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            total_tokens = None
            if response.usage:
                total_tokens = response.usage.input_tokens + response.usage.output_tokens

            return ChatResponse(
                content=content,
                model=model,
                provider=self.name,
                tokens_used=total_tokens,
                finish_reason=response.stop_reason,
            )
        except Exception as e:
            logger.error("Anthropic chat error", error=str(e), model=model)
            raise

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Anthropic."""
        if not self.is_configured:
            raise ValueError("Anthropic API key not configured")

        client = self._get_client()

        formatted_messages = []
        for msg in messages:
            if msg.role.value != "system":
                formatted_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        try:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens or 4096,
                system=system_prompt or "",
                messages=formatted_messages,
                temperature=temperature,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error("Anthropic stream error", error=str(e), model=model)
            raise

    async def list_models(self) -> list[ModelInfo]:
        """List known Anthropic models."""
        models = []
        for model_id, info in ANTHROPIC_MODELS.items():
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                context_window=info["context"],
                capabilities=info["capabilities"],
            ))
        return models

    async def health_check(self) -> bool:
        """Check if Anthropic is accessible."""
        if not self.is_configured:
            return False
        try:
            # Simple test with minimal tokens
            client = self._get_client()
            await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True
        except Exception as e:
            logger.warning("Anthropic health check failed", error=str(e))
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=True,
            supports_embeddings=False,  # Anthropic doesn't offer embeddings
            max_context_window=200000,
        )
