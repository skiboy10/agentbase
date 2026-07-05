"""
RAG Service - Re-export from modular package.

This file exists for backward compatibility. Import from app.services.rag instead.
"""
from app.services.rag import (
    RAGService,
    SearchResult,
    RAGSource,
    RAGContext,
    reciprocal_rank_fusion,
    weighted_rrf,
    get_qdrant_client,
)

__all__ = [
    "RAGService",
    "SearchResult",
    "RAGSource",
    "RAGContext",
    "reciprocal_rank_fusion",
    "weighted_rrf",
    "get_qdrant_client",
]
