"""
Abstract base class for LLM providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Optional


class MessageRole(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ChatMessage:
    """A message in a chat conversation."""
    role: MessageRole
    content: str


@dataclass
class ChatResponse:
    """Response from an LLM provider."""
    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None


@dataclass
class ProviderCapabilities:
    """Capabilities of an LLM provider."""
    supports_streaming: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    max_context_window: int = 4096


@dataclass
class ModelInfo:
    """Information about a specific model."""
    id: str
    name: str
    provider: str
    context_window: int = 4096
    capabilities: list[str] = field(default_factory=list)


@dataclass
class EmbeddingModelInfo:
    """Information about an embedding model."""
    id: str
    name: str
    provider: str
    dimensions: int
    max_input_tokens: int = 8192


@dataclass
class EmbeddingResponse:
    """Response from an embedding request."""
    embeddings: list[list[float]]
    model: str
    provider: str
    total_tokens: Optional[int] = None
    dimensions: int = 0


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All provider implementations must inherit from this class and implement
    the abstract methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'ollama', 'openai')."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider is properly configured (has API key, etc.)."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """
        Send a chat request and get a response.

        Args:
            messages: List of chat messages
            model: Model identifier to use
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            system_prompt: Optional system prompt to prepend

        Returns:
            ChatResponse with the model's response
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Send a chat request and stream the response.

        Args:
            messages: List of chat messages
            model: Model identifier to use
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            system_prompt: Optional system prompt to prepend

        Yields:
            Response text chunks as they arrive
        """
        pass

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """
        List available models from this provider.

        Returns:
            List of available model information
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is accessible and responding.

        Returns:
            True if provider is healthy, False otherwise
        """
        pass

    def get_capabilities(self) -> ProviderCapabilities:
        """
        Get the capabilities of this provider.

        Override in subclasses to provide accurate capabilities.
        """
        return ProviderCapabilities()
