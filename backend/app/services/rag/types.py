"""
RAG Service types - Data classes for search results and context.
"""
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """A single search result from the knowledge base.

    Top-level fields provide everything a calling LLM needs for citation
    without digging into the metadata dict:

        title         — Human-readable document title (falls back to "" if unknown)
        source_name   — Display name of the KnowledgeSource (e.g. "Company Wiki")
        document_path — Clean file path or URL (same as source but explicitly named)
        collection    — Qdrant collection name the chunk came from

    The ``metadata`` dict still carries secondary payload fields (chunk_index,
    content_hash, embedding_model, etc.) for callers that need them.
    """
    content: str
    source: str           # Raw payload value — keep for backward compat
    score: float
    metadata: dict
    # Enriched top-level fields for citation and filtering
    title: str = ""
    source_name: str = ""
    document_path: str = ""   # Clean file path or URL
    collection: str = ""
    # Cross-encoder rerank score (None when reranking was not applied)
    rerank_score: float | None = None


@dataclass
class SubQuery:
    """A decomposed sub-query with optional metadata filters and strategy tag."""
    query: str
    filters: dict = field(default_factory=dict)
    strategy: str = "original"  # entity, aspect, temporal, abstraction, original


@dataclass
class DeepSearchResult:
    """Result from deep_search including decomposition metadata."""
    results: list[SearchResult]
    sub_queries: list[SubQuery]
    stats: dict = field(default_factory=dict)


@dataclass
class RAGSource:
    """A source used in RAG context."""
    url: str
    title: str
    source_name: str
    preview: str  # First ~200 chars of content


@dataclass
class RAGContext:
    """Formatted context for injection into LLM prompt."""
    text: str
    sources: list[str]  # Unique source URLs (for backward compat)
    source_details: list[RAGSource]  # Detailed source info for attribution
    result_count: int
