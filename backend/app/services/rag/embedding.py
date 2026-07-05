"""
Embedding utilities for RAG service.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.providers.embedding_registry import get_embedding_registry

settings = get_settings()


async def get_embedding_config(db: AsyncSession) -> tuple[str, str, int]:
    """
    Get the configured embedding provider, model, and vector size.

    Returns:
        Tuple of (provider, model, dimensions)
    """
    from app.models import ModelAssignment

    registry = get_embedding_registry()

    # Check for embedding assignment
    stmt = select(ModelAssignment).where(
        ModelAssignment.project_id.is_(None),
        ModelAssignment.task_type == "embedding"
    )
    result = await db.execute(stmt)
    assignment = result.scalars().first()

    if assignment:
        provider = assignment.provider
        model = assignment.model
    else:
        provider = settings.embedding_provider
        model = settings.embedding_model

    # Get vector size from registry
    emb_provider = registry.get_provider(provider)
    if emb_provider:
        dimensions = emb_provider.get_model_dimensions(model)
        return provider, model, dimensions

    # Default fallback
    return provider, model, 1536


async def embed_query(db: AsyncSession, query: str) -> list[float]:
    """Generate embedding for a query string using default config."""
    registry = get_embedding_registry()
    provider, model, _ = await get_embedding_config(db)

    response = await registry.embed(provider, model, [query], input_type="query")
    return response.embeddings[0]


async def embed_query_with_model(
    query: str,
    provider: str,
    model: str
) -> list[float]:
    """
    Generate embedding for a query string using a specific provider/model.

    Args:
        query: The text to embed
        provider: Embedding provider name (e.g., "ollama", "openai")
        model: Embedding model name (e.g., "mxbai-embed-large")

    Returns:
        List of floats representing the embedding vector
    """
    registry = get_embedding_registry()
    response = await registry.embed(provider, model, [query], input_type="query")
    return response.embeddings[0]
