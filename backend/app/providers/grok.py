"""
Grok (xAI) provider implementation.
"""
from typing import AsyncGenerator, Optional
import httpx
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

# Known Grok models
GROK_MODELS = {
    # Grok-4 series
    "grok-4-0709": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    "grok-4-fast-reasoning": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    "grok-4-fast-non-reasoning": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    "grok-4-1-fast-reasoning": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    "grok-4-1-fast-non-reasoning": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    # Grok-3 series
    "grok-3": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    "grok-3-mini": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    # Grok-2 series
    "grok-2": {"context": 131072, "capabilities": ["coding", "reasoning"]},
    "grok-2-vision-1212": {"context": 131072, "capabilities": ["coding", "reasoning", "vision"]},
    "grok-2-image-1212": {"context": 131072, "capabilities": ["coding", "reasoning", "vision"]},
    # Specialized
    "grok-code-fast-1": {"context": 131072, "capabilities": ["coding"]},
}


class GrokProvider(LLMProvider):
    """
    Grok (xAI) API provider.

    Uses OpenAI-compatible API format.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.grok_api_key
        self.base_url = base_url or settings.grok_base_url
        self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client for Grok API."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    @property
    def name(self) -> str:
        return "grok"

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
        """Send chat request to Grok."""
        if not self.is_configured:
            raise ValueError("Grok API key not configured")

        client = self._get_client()
        formatted_messages = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            formatted_messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": False,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            return ChatResponse(
                content=data["choices"][0]["message"]["content"],
                model=model,
                provider=self.name,
                tokens_used=data.get("usage", {}).get("total_tokens"),
                finish_reason=data["choices"][0].get("finish_reason"),
            )
        except httpx.HTTPError as e:
            logger.error("Grok chat error", error=str(e), model=model)
            raise

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Grok."""
        if not self.is_configured:
            raise ValueError("Grok API key not configured")

        client = self._get_client()
        formatted_messages = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            formatted_messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        import json
                        data = json.loads(data_str)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
        except httpx.HTTPError as e:
            logger.error("Grok stream error", error=str(e), model=model)
            raise

    async def list_models(self) -> list[ModelInfo]:
        """List known Grok models."""
        models = []
        for model_id, info in GROK_MODELS.items():
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                context_window=info["context"],
                capabilities=info["capabilities"],
            ))
        return models

    async def health_check(self) -> bool:
        """Check if Grok is accessible."""
        if not self.is_configured:
            return False
        try:
            client = self._get_client()
            response = await client.get("/models")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Grok health check failed", error=str(e))
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=False,
            supports_embeddings=False,
            max_context_window=131072,
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
