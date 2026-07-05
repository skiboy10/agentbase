"""
RAG Service package.

Provides retrieval-augmented generation functionality:
- Query embedding generation
- Semantic search over knowledge base (standard, hybrid, grouped)
- Deep search with query decomposition
- Cross-encoder reranking via Ollama
- Context formatting for LLM consumption
- Chunk neighbor fetching for context windowing
- Filter value discovery for metadata filtering
"""
from .types import SearchResult, SubQuery, DeepSearchResult, RAGSource, RAGContext
from .fusion import reciprocal_rank_fusion, weighted_rrf
from .client import get_qdrant_client
from .service import RAGService
from .reranker import RerankerService
from .decomposer import QueryDecomposer
from .neighbors import fetch_chunk_neighbors, list_unique_field_values

__all__ = [
    # Main service
    "RAGService",
    # Types
    "SearchResult",
    "SubQuery",
    "DeepSearchResult",
    "RAGSource",
    "RAGContext",
    # Utilities
    "reciprocal_rank_fusion",
    "weighted_rrf",
    "get_qdrant_client",
    # Reranking
    "RerankerService",
    # Decomposition
    "QueryDecomposer",
    # Neighbor/context windowing
    "fetch_chunk_neighbors",
    "list_unique_field_values",
]
