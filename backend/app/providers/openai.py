"""
OpenAI provider implementation.
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

# Known OpenAI models and their context windows
OPENAI_MODELS = {
    # GPT-5 series
    "gpt-5.2": {"context": 256000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-5.2-pro": {"context": 256000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-5.1": {"context": 256000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-5": {"context": 256000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-5-pro": {"context": 256000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-5-mini": {"context": 128000, "capabilities": ["coding", "reasoning"]},
    "gpt-5-nano": {"context": 64000, "capabilities": ["coding", "reasoning"]},
    # GPT-4.1 series
    "gpt-4.1": {"context": 128000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-4.1-mini": {"context": 128000, "capabilities": ["coding", "reasoning"]},
    "gpt-4.1-nano": {"context": 64000, "capabilities": ["coding", "reasoning"]},
    # GPT-4 series
    "gpt-4o": {"context": 128000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-4o-mini": {"context": 128000, "capabilities": ["coding", "reasoning"]},
    "gpt-4-turbo": {"context": 128000, "capabilities": ["coding", "reasoning", "vision"]},
    "gpt-4": {"context": 8192, "capabilities": ["coding", "reasoning"]},
    "gpt-3.5-turbo": {"context": 16385, "capabilities": ["coding"]},
    # O-series reasoning models
    "o4-mini": {"context": 200000, "capabilities": ["reasoning", "coding"]},
    "o3": {"context": 200000, "capabilities": ["reasoning", "coding"]},
    "o3-mini": {"context": 200000, "capabilities": ["reasoning", "coding"]},
    "o3-pro": {"context": 200000, "capabilities": ["reasoning", "coding"]},
    "o1": {"context": 200000, "capabilities": ["reasoning", "coding"]},
    "o1-pro": {"context": 200000, "capabilities": ["reasoning", "coding"]},
}

# Models that only support temperature=1.0 (no custom temperature allowed)
# These are typically reasoning-focused or efficiency models
TEMPERATURE_RESTRICTED_MODELS = {
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o4-mini",
    "o3",
    "o3-mini",
    "o3-pro",
    "o1",
    "o1-pro",
}


def _normalize_temperature(model: str, temperature: float) -> float:
    """
    Normalize temperature for models that don't support custom values.

    Some OpenAI models (mini, nano, o-series) only support temperature=1.0.
    This function ensures compatibility by returning 1.0 for restricted models.
    """
    # Check if model matches any restricted pattern (handles version suffixes)
    for restricted in TEMPERATURE_RESTRICTED_MODELS:
        if model == restricted or model.startswith(f"{restricted}-"):
            if temperature != 1.0:
                logger.info(
                    "Normalizing temperature for restricted model",
                    model=model,
                    requested_temp=temperature,
                    normalized_temp=1.0,
                )
            return 1.0
    return temperature


class OpenAIProvider(LLMProvider):
    """
    OpenAI API provider.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            import httpx
            # 120 second timeout for API calls (prevents infinite hangs)
            timeout = httpx.Timeout(120.0, connect=10.0)
            self._client = AsyncOpenAI(api_key=self.api_key, timeout=timeout)
        return self._client

    @property
    def name(self) -> str:
        return "openai"

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
        """Send chat request to OpenAI."""
        if not self.is_configured:
            raise ValueError("OpenAI API key not configured")

        client = self._get_client()
        formatted_messages = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            formatted_messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        try:
            # Normalize temperature for models that don't support custom values
            effective_temp = _normalize_temperature(model, temperature)

            # Build request kwargs, only include max_tokens if set
            request_kwargs = {
                "model": model,
                "messages": formatted_messages,
                "temperature": effective_temp,
            }
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens

            response = await client.chat.completions.create(**request_kwargs)

            # Log model routing verification (actual vs requested)
            actual_model = response.model
            tokens_used = response.usage.total_tokens if response.usage else None

            # Check if models match (OpenAI adds version suffixes like -2025-12-11)
            models_match = (
                actual_model == model or
                actual_model.startswith(f"{model}-") or
                model.startswith(f"{actual_model}-")
            )

            if not models_match:
                # True mismatch - different model family
                print(f"⚠️  MODEL ROUTING MISMATCH: requested={model}, actual={actual_model}, tokens={tokens_used}", flush=True)
                logger.warning(
                    "Model routing mismatch",
                    requested=model,
                    actual=actual_model,
                    tokens=tokens_used,
                )
            else:
                # Same model family (possibly with version suffix)
                print(f"✓ OpenAI model OK: requested={model}, actual={actual_model}, tokens={tokens_used}", flush=True)

            return ChatResponse(
                content=response.choices[0].message.content,
                model=actual_model,  # Return actual model used, not requested
                provider=self.name,
                tokens_used=response.usage.total_tokens if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
            )
        except Exception as e:
            logger.error("OpenAI chat error", error=str(e), model=model)
            raise

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from OpenAI."""
        if not self.is_configured:
            raise ValueError("OpenAI API key not configured")

        client = self._get_client()
        formatted_messages = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            formatted_messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        try:
            # Normalize temperature for models that don't support custom values
            effective_temp = _normalize_temperature(model, temperature)

            # Build request kwargs, only include max_tokens if set
            request_kwargs = {
                "model": model,
                "messages": formatted_messages,
                "temperature": effective_temp,
                "stream": True,
            }
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens

            logger.info("OpenAI stream request", requested_model=model)
            stream = await client.chat.completions.create(**request_kwargs)

            actual_model = None
            async for chunk in stream:
                # First chunk contains the actual model
                if actual_model is None and hasattr(chunk, 'model'):
                    actual_model = chunk.model
                    if actual_model != model:
                        logger.warning(
                            "Stream model routing mismatch",
                            requested=model,
                            actual=actual_model,
                        )
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error("OpenAI stream error", error=str(e), model=model)
            raise

    async def list_models(self) -> list[ModelInfo]:
        """List known OpenAI models."""
        # OpenAI doesn't have a great way to list chat models,
        # so we use a predefined list
        models = []
        for model_id, info in OPENAI_MODELS.items():
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                context_window=info["context"],
                capabilities=info["capabilities"],
            ))
        return models

    async def health_check(self) -> bool:
        """Check if OpenAI is accessible."""
        if not self.is_configured:
            return False
        try:
            client = self._get_client()
            # Simple models list call to verify API key
            await client.models.list()
            return True
        except Exception as e:
            logger.warning("OpenAI health check failed", error=str(e))
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=True,
            supports_embeddings=True,
            max_context_window=128000,
        )
