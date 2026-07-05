"""
Ollama provider implementation for local models.
"""
import json
from typing import AsyncGenerator, Optional
import httpx
import structlog

from app.providers.base import (
    LLMProvider,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
    MessageRole,
)
from app.core.config import get_settings

logger = structlog.get_logger()


class OllamaProvider(LLMProvider):
    """
    Ollama provider for running local LLM models.

    Ollama must be running locally or accessible via the configured base URL.
    """

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def is_configured(self) -> bool:
        # Ollama doesn't need API key, just needs to be accessible
        return True

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Send chat request to Ollama."""
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
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # qwen3 and gemma4 families use extended thinking by default; disable it
        # so responses are clean text — thinking models can burn the whole
        # num_predict budget in the thinking channel and return empty content.
        if model.startswith(("qwen3", "gemma4")):
            payload["think"] = False

        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

            return ChatResponse(
                content=data["message"]["content"],
                model=model,
                provider=self.name,
                tokens_used=data.get("eval_count"),
                finish_reason="stop",
            )
        except httpx.HTTPStatusError as e:
            logger.error("Ollama chat error", error=str(e), model=model)
            if e.response.status_code == 404:
                # Ollama returns 404 from /api/chat when the model isn't
                # pulled — surface an actionable message instead of the raw
                # httpx error (#176).
                raise ValueError(
                    f"Model '{model}' not found on Ollama — pull it "
                    f"(ollama pull {model}) or update the agent's model"
                ) from e
            raise
        except httpx.HTTPError as e:
            logger.error("Ollama chat error", error=str(e), model=model)
            raise

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Ollama."""
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
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # qwen3 and gemma4 families use extended thinking by default; disable it
        # for clean output (see chat() note on empty-content risk).
        if model.startswith(("qwen3", "gemma4")):
            payload["think"] = False

        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error("Ollama stream error", error=str(e), model=model)
            if e.response.status_code == 404:
                # Same model-not-found mapping as chat() (#176)
                raise ValueError(
                    f"Model '{model}' not found on Ollama — pull it "
                    f"(ollama pull {model}) or update the agent's model"
                ) from e
            raise
        except httpx.HTTPError as e:
            logger.error("Ollama stream error", error=str(e), model=model)
            raise

    async def list_models(self) -> list[ModelInfo]:
        """List models available in Ollama."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("models", []):
                model_name = model_data["name"]
                # Extract capabilities from model name
                capabilities = []
                if "code" in model_name.lower():
                    capabilities.append("coding")
                if "instruct" in model_name.lower():
                    capabilities.append("instruction-following")

                models.append(ModelInfo(
                    id=model_name,
                    name=model_name,
                    provider=self.name,
                    context_window=model_data.get("context_length", 4096),
                    capabilities=capabilities,
                ))

            return models
        except httpx.HTTPError as e:
            logger.error("Ollama list models error", error=str(e))
            return []

    async def health_check(self) -> bool:
        """Check if Ollama is accessible."""
        try:
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Ollama health check failed", error=str(e))
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=False,  # Depends on model
            supports_vision=False,  # Depends on model
            supports_embeddings=True,
            max_context_window=4096,  # Varies by model
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
