"""
Pydantic schemas for Sources API.

All request/response models for source management.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ==================== Request Schemas ====================

class SourceCreate(BaseModel):
    """Source creation request."""
    name: str
    source_type: str  # "url", "file", "directory", "youtube"
    source_path: str
    project_id: Optional[str] = None
    selected_urls: Optional[list[str]] = None
    description: Optional[str] = None
    # Optional embedding override (uses default if not specified)
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    # Enrichment pipeline config
    enrichment_enabled: bool = False
    enrichment_taxonomy_id: Optional[str] = None
    enrichment_model: Optional[str] = None
    # Directory watcher config
    watch_enabled: bool = False
    watch_extensions: Optional[list[str]] = None
    watch_mode: str = "auto"
    watch_poll_interval_seconds: int = 300
    watch_debounce_seconds: int = 60
    watch_max_file_size_mb: int = 50
    # Freshness lifecycle
    freshness_policy: Optional[str] = None  # "none" | "automatic" | "manual"
    stale_after_days: Optional[int] = None
    refresh_interval_days: Optional[int] = None
    # YouTube source config (source_type="youtube"). source_path is the channel
    # URL; these control how much of the back catalogue to ingest, per channel.
    youtube_backfill_mode: Optional[str] = None  # "all" | "recent"
    youtube_recent_count: Optional[int] = None
    # Sub-source model: when parent_source_id is set, this Source is a
    # filtered view over the parent root (no own collection, no own watcher).
    parent_source_id: Optional[str] = None
    path_prefix: Optional[str] = None
    path_excludes: Optional[list[str]] = None


class SourceUpdate(BaseModel):
    """Source update request."""
    name: Optional[str] = None
    description: Optional[str] = None
    # Watcher configuration (all fields updatable post-creation)
    watch_enabled: Optional[bool] = None
    watch_extensions: Optional[list[str]] = None
    watch_mode: Optional[str] = None
    watch_poll_interval_seconds: Optional[int] = None
    watch_debounce_seconds: Optional[int] = None
    watch_max_file_size_mb: Optional[int] = None
    watch_depth: Optional[int] = None
    # Enrichment configuration
    enrichment_enabled: Optional[bool] = None
    enrichment_taxonomy_id: Optional[str] = None
    enrichment_model: Optional[str] = None
    # Freshness lifecycle
    freshness_policy: Optional[str] = None
    stale_after_days: Optional[int] = None
    refresh_interval_days: Optional[int] = None
    # YouTube source config (depth editable post-creation)
    youtube_backfill_mode: Optional[str] = None
    youtube_recent_count: Optional[int] = None
    # Sub-source / path overlay (re-parenting via parent_source_id is not allowed)
    path_prefix: Optional[str] = None
    path_excludes: Optional[list[str]] = None


class AddUrlsRequest(BaseModel):
    """Request to add URLs to a source."""
    urls: list[str]


class RemoveUrlsRequest(BaseModel):
    """Request to remove URLs from a source."""
    urls: list[str]


class RemoveFilesRequest(BaseModel):
    """Request to remove files from a source."""
    file_paths: list[str]


class RefreshSourceRequest(BaseModel):
    """Request to refresh a source."""
    mode: str = "full"  # "full" or "selective"
    urls: Optional[list[str]] = None  # For selective mode
    force: bool = False  # Override "already_indexing" guard for stalled jobs


class AdoptCollectionRequest(BaseModel):
    """Request to adopt an existing Qdrant collection."""
    name: str  # User-friendly name for the source
    collection_name: str  # Existing Qdrant collection name
    description: Optional[str] = None
    project_id: Optional[str] = None
    # Required embedding configuration (must match what was used to create the collection)
    embedding_provider: str  # e.g., "ollama", "openai"
    embedding_model: str  # e.g., "mxbai-embed-large", "text-embedding-3-small"
    embedding_dimensions: int  # e.g., 1024, 1536
    # Optional enrichment. Adoption skips indexing, so when enabled the caller
    # is responsible for triggering POST /api/sources/{id}/re-enrich after
    # create so existing chunks get classified against the chosen taxonomy.
    enrichment_enabled: bool = False
    enrichment_taxonomy_id: Optional[str] = None
    enrichment_model: Optional[str] = None


class SearchRequest(BaseModel):
    """Search request."""
    query: str
    project_id: Optional[str] = None
    top_k: int = 5
    hybrid: bool = True  # Enable hybrid search by default
    vector_weight: float = 0.7  # Weight for vector vs text (0-1)
    source_ids: Optional[list[str]] = None  # Filter to specific sources
    knowledge_base_id: Optional[str] = None  # Search all sources in a Library (mutually exclusive with source_ids)
    filters: Optional[dict] = None  # Metadata filters: {"platforms": ["AcmeCRM"], "doc_category": "proposal"}
    rerank: bool = True  # Apply cross-encoder reranking after retrieval (opt-out with false)
    include_neighbors: int = 0  # Number of neighboring chunks to include around each result (0=off)

    @model_validator(mode="after")
    def check_source_scope_exclusivity(self):
        if self.source_ids and self.knowledge_base_id:
            raise ValueError("source_ids and knowledge_base_id are mutually exclusive")
        return self


class DeepSearchRequest(BaseModel):
    """Deep search request with query decomposition."""
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    max_sub_queries: int = Field(default=5, ge=1, le=10)
    source_ids: Optional[list[str]] = None
    knowledge_base_id: Optional[str] = None  # Search all sources in a Library (mutually exclusive with source_ids)
    filters: Optional[dict] = None
    rerank: bool = True
    include_decomposition: bool = False

    @model_validator(mode="after")
    def check_source_scope_exclusivity(self):
        if self.source_ids and self.knowledge_base_id:
            raise ValueError("source_ids and knowledge_base_id are mutually exclusive")
        return self


class ScanUrlRequest(BaseModel):
    """URL scan request."""
    url: str
    max_depth: int = 2
    path_scope: Optional[str] = None
    sitemap_url: Optional[str] = None
    path_filter: Optional[str] = None
    auto_discover_sitemap: bool = False


# ==================== Response Schemas ====================

class ProjectInfo(BaseModel):
    """Minimal project info for assignments."""
    id: str
    name: str


class AgentInfo(BaseModel):
    """Minimal agent info for source bindings."""
    id: str
    name: str


class FileInfo(BaseModel):
    """File metadata for file-type sources."""
    path: str
    original_name: str
    size_bytes: int


class SourceResponse(BaseModel):
    """Source response."""
    id: str
    name: str
    description: Optional[str] = None
    source_type: str
    source_path: str
    project_id: Optional[str]
    status: str
    last_indexed: Optional[datetime]
    document_count: int
    chunk_count: int
    error_message: Optional[str]
    progress: int = 0
    progress_total: int = 0
    progress_message: Optional[str] = None
    progress_updated_at: Optional[datetime] = None
    created_at: datetime
    selected_urls: Optional[list[str]] = None  # For URL sources
    selected_files: Optional[list[FileInfo]] = None  # For file sources
    # Qdrant collection name
    collection_name: Optional[str] = None
    # Embedding configuration used for this source
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None
    # Project assignments (for global sources)
    assigned_projects: list[ProjectInfo] = []
    # Owner project info (for project-specific sources)
    owner_project: Optional[ProjectInfo] = None
    # Agents that use this source
    bound_agents: list[AgentInfo] = []
    # Enrichment pipeline config
    enrichment_enabled: bool = False
    enrichment_taxonomy_id: Optional[str] = None
    enrichment_model: Optional[str] = None
    # Directory watcher config
    watch_enabled: bool = False
    watch_extensions: Optional[list[str]] = None
    watch_mode: Optional[str] = None
    watch_poll_interval_seconds: Optional[int] = None
    watch_debounce_seconds: Optional[int] = None
    watch_max_file_size_mb: Optional[int] = None
    watch_depth: Optional[int] = None
    # Watcher runtime state
    watch_status: Optional[str] = None
    watch_last_heartbeat_at: Optional[datetime] = None
    watch_last_error: Optional[str] = None
    # Freshness lifecycle
    freshness_policy: Optional[str] = None
    stale_after_days: Optional[int] = None
    refresh_interval_days: Optional[int] = None
    next_refresh_at: Optional[datetime] = None
    freshness_status: Optional[str] = None  # Computed: "current" | "aging" | "stale"
    # YouTube source config
    youtube_backfill_mode: Optional[str] = None  # "all" | "recent"
    youtube_recent_count: Optional[int] = None
    # Sub-source model
    parent_source_id: Optional[str] = None
    path_prefix: Optional[str] = None
    path_excludes: Optional[list[str]] = None
    sub_source_count: int = 0  # 0 for sub-sources; N children for roots

    class Config:
        from_attributes = True


# Backward-compatible alias
KnowledgeSourceResponse = SourceResponse
KnowledgeSourceCreate = SourceCreate
KnowledgeSourceUpdate = SourceUpdate


class SearchResult(BaseModel):
    """Search result from sources."""
    content: str
    source: str
    score: float
    metadata: dict = {}
    # Enriched fields promoted to top-level for easy citation
    title: str = ""
    source_name: str = ""
    document_path: str = ""
    collection: str = ""
    rerank_score: float | None = None
    # Neighboring chunks for context windowing (only present when include_neighbors > 0)
    context_chunks: Optional[list[dict]] = None


class SubQueryResponse(BaseModel):
    """A decomposed sub-query."""
    query: str
    filters: dict = {}
    strategy: str = "original"


class DeepSearchResponse(BaseModel):
    """Deep search response with decomposition metadata."""
    results: list[SearchResult]
    sub_queries: list[SubQueryResponse] = []
    stats: dict = {}


class SiteTreeNode(BaseModel):
    """Node in the site tree structure."""
    url: str
    title: str
    path: str
    children: list['SiteTreeNode'] = []

    class Config:
        from_attributes = True


SiteTreeNode.model_rebuild()


class ScanUrlResponse(BaseModel):
    """Response from URL scan."""
    tree: SiteTreeNode
    sitemap_url: Optional[str] = None


class IndexingStatusResponse(BaseModel):
    """Lightweight status response for polling during indexing."""
    source_id: str
    status: str
    progress: int
    progress_total: int
    progress_message: Optional[str]
    progress_updated_at: Optional[datetime]
    document_count: int
    chunk_count: int
    error_message: Optional[str]


class IndexingLogResponse(BaseModel):
    """Individual indexing log entry."""
    id: str
    source_id: str
    url: str
    status: str
    error_message: Optional[str]
    scrape_duration_ms: Optional[int]
    embed_duration_ms: Optional[int]
    content_length: Optional[int]
    chunk_count: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IndexingLogsResponse(BaseModel):
    """Response for indexing logs with summary stats."""
    logs: list[IndexingLogResponse]
    summary: dict


class QdrantCollectionInfo(BaseModel):
    """Detailed information about a Qdrant collection."""
    name: str
    vectors_count: int
    points_count: int
    vector_size: Optional[int] = None
    distance: Optional[str] = None
    is_linked: bool = False  # Whether linked to a source
    linked_source_id: Optional[str] = None
    linked_source_name: Optional[str] = None
