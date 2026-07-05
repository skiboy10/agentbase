"""
Configuration API endpoints.

Provides endpoints for retrieving system configuration.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.core.config import get_settings
from app.services import RAGService
from app.providers.embedding_registry import get_embedding_registry

router = APIRouter()
settings = get_settings()


class EmbeddingModelInfo(BaseModel):
    """Information about an available embedding model."""
    provider: str
    model: str
    dimensions: int


class EmbeddingConfigResponse(BaseModel):
    """Embedding configuration response."""
    default_provider: str
    default_model: str
    available_models: list[EmbeddingModelInfo]


@router.get("/embedding", response_model=EmbeddingConfigResponse)
async def get_embedding_config(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get embedding configuration including default and available models."""
    rag_service = RAGService(db)
    # get_embedding_config returns a tuple: (provider, model, dimensions)
    provider, model, _ = await rag_service.get_embedding_config()

    # Get models dynamically from the embedding registry
    registry = get_embedding_registry()
    registry_models = await registry.list_all_embedding_models()

    available = [
        EmbeddingModelInfo(provider=m.provider, model=m.id, dimensions=m.dimensions)
        for m in registry_models
    ]

    return EmbeddingConfigResponse(
        default_provider=provider,
        default_model=model,
        available_models=available,
    )
