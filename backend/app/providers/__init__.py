"""
LLM Provider implementations.

This module provides a unified interface for interacting with different LLM providers:
- Ollama (local models)
- OpenAI
- Anthropic
- Grok (xAI)

And embedding providers:
- OpenAI
- Ollama
"""
from app.providers.base import (
    LLMProvider,
    ChatMessage,
    ChatResponse,
    ProviderCapabilities,
    EmbeddingModelInfo,
    EmbeddingResponse,
)
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.grok import GrokProvider
from app.providers.registry import ProviderRegistry, get_registry
from app.providers.embedding_base import EmbeddingProvider
from app.providers.embedding_openai import OpenAIEmbeddingProvider
from app.providers.embedding_ollama import OllamaEmbeddingProvider
from app.providers.embedding_registry import EmbeddingRegistry, get_embedding_registry

__all__ = [
    # LLM Provider base
    "LLMProvider",
    "ChatMessage",
    "ChatResponse",
    "ProviderCapabilities",
    # LLM Providers
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GrokProvider",
    "ProviderRegistry",
    "get_registry",
    # Embedding base
    "EmbeddingProvider",
    "EmbeddingModelInfo",
    "EmbeddingResponse",
    # Embedding Providers
    "OpenAIEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "EmbeddingRegistry",
    "get_embedding_registry",
]
