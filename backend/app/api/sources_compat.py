"""
Backward compatibility re-exports from modular sources/ directory.

The sources router has been split into:
- sources/schemas.py: Pydantic request/response models
- sources/helpers.py: Response conversion utilities
- sources/sources.py: Source CRUD endpoints
- sources/indexing.py: Indexing operations
- sources/operations.py: Scan/search/collections

Import from app.api.sources for current imports,
or directly from app.api.sources.* for explicit imports.
"""
# Re-export router from the sources package
from app.api.sources import router

# Re-export all schemas for backward compatibility
from app.api.sources.schemas import (
    # Request schemas
    SourceCreate,
    SourceUpdate,
    AddUrlsRequest,
    RemoveUrlsRequest,
    RefreshSourceRequest,
    AdoptCollectionRequest,
    SearchRequest,
    ScanUrlRequest,
    # Response schemas
    ProjectInfo,
    SourceResponse,
    SearchResult,
    SiteTreeNode,
    ScanUrlResponse,
    IndexingStatusResponse,
    IndexingLogResponse,
    IndexingLogsResponse,
    QdrantCollectionInfo,
    # Backward-compatible aliases
    KnowledgeSourceCreate,
    KnowledgeSourceUpdate,
    KnowledgeSourceResponse,
)

# Re-export helpers for backward compatibility
from app.api.sources.helpers import source_to_response, tree_to_response

# Backward-compatible aliases for internal helper function names
_source_to_response = source_to_response
_tree_to_response = tree_to_response

__all__ = [
    "router",
    # New names
    "SourceCreate",
    "SourceUpdate",
    "SourceResponse",
    # Legacy aliases
    "KnowledgeSourceCreate",
    "KnowledgeSourceUpdate",
    "KnowledgeSourceResponse",
    # Other schemas
    "AddUrlsRequest",
    "RemoveUrlsRequest",
    "RefreshSourceRequest",
    "AdoptCollectionRequest",
    "SearchRequest",
    "ScanUrlRequest",
    "ProjectInfo",
    "SearchResult",
    "SiteTreeNode",
    "ScanUrlResponse",
    "IndexingStatusResponse",
    "IndexingLogResponse",
    "IndexingLogsResponse",
    "QdrantCollectionInfo",
    # Helpers
    "source_to_response",
    "tree_to_response",
    "_source_to_response",
    "_tree_to_response",
]
