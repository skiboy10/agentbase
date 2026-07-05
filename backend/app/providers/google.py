"""
Google AI (Gemini) provider implementation.
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

# Known Gemini models and their context windows
GOOGLE_MODELS = {
    "gemini-2.0-flash-exp": {"context": 1000000, "capabilities": ["coding", "reasoning", "vision"]},
    "gemini-1.5-pro": {"context": 2000000, "capabilities": ["coding", "reasoning", "vision"]},
    "gemini-1.5-flash": {"context": 1000000, "capabilities": ["coding", "reasoning", "vision"]},
    "gemini-1.5-flash-8b": {"context": 1000000, "capabilities": ["coding", "reasoning"]},
    "gemini-1.0-pro": {"context": 32000, "capabilities": ["coding", "reasoning"]},
}


class GoogleProvider(LLMProvider):
    """
    Google AI (Gemini) API provider.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.google_api_key
        self._client = None

    def _get_client(self):
        """Lazy initialization of Google AI client."""
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai
        return self._client

    @property
    def name(self) -> str:
        return "google"

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
        """Send chat request to Google AI."""
        if not self.is_configured:
            raise ValueError("Google AI API key not configured")

        genai = self._get_client()

        # Create the model with system instruction if provided
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        model_instance = genai.GenerativeModel(
            model_name=model,
            generation_config=generation_config,
            system_instruction=system_prompt if system_prompt else None,
        )

        # Convert messages to Gemini format
        history = []
        last_message = None

        for msg in messages:
            role = "user" if msg.role.value == "user" else "model"
            if msg == messages[-1]:
                last_message = msg.content
            else:
                history.append({"role": role, "parts": [msg.content]})

        try:
            chat = model_instance.start_chat(history=history)
            response = await chat.send_message_async(last_message)

            return ChatResponse(
                content=response.text,
                model=model,
                provider=self.name,
                tokens_used=None,  # Gemini doesn't easily provide token counts
                finish_reason="stop",
            )
        except Exception as e:
            logger.error("Google AI chat error", error=str(e), model=model)
            raise

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Google AI."""
        if not self.is_configured:
            raise ValueError("Google AI API key not configured")

        genai = self._get_client()

        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        model_instance = genai.GenerativeModel(
            model_name=model,
            generation_config=generation_config,
            system_instruction=system_prompt if system_prompt else None,
        )

        # Convert messages to Gemini format
        history = []
        last_message = None

        for msg in messages:
            role = "user" if msg.role.value == "user" else "model"
            if msg == messages[-1]:
                last_message = msg.content
            else:
                history.append({"role": role, "parts": [msg.content]})

        try:
            chat = model_instance.start_chat(history=history)
            response = await chat.send_message_async(last_message, stream=True)

            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error("Google AI stream error", error=str(e), model=model)
            raise

    async def list_models(self) -> list[ModelInfo]:
        """List known Google AI models."""
        models = []
        for model_id, info in GOOGLE_MODELS.items():
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                context_window=info["context"],
                capabilities=info["capabilities"],
            ))
        return models

    async def health_check(self) -> bool:
        """Check if Google AI is accessible."""
        if not self.is_configured:
            return False
        try:
            import asyncio
            genai = self._get_client()
            # list_models() is a synchronous call — run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: list(genai.list_models()))
            return True
        except Exception as e:
            logger.warning("Google AI health check failed", error=str(e))
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=True,
            supports_embeddings=True,
            max_context_window=2000000,
        )
