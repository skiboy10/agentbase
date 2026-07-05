"""
Backward compatibility re-exports from modular ingestion/ package.

The ingestion service has been split into:
- ingestion/types.py: Data classes (SiteTreeNode, ScanResult, etc.)
- ingestion/qdrant_client.py: Qdrant client singleton
- ingestion/embedding_processor.py: Shared embedding operations
- ingestion/source_manager.py: Source CRUD operations
- ingestion/log_manager.py: Indexing log operations
- ingestion/url_scanner.py: URL structure scanning
- ingestion/orchestrator.py: Main IngestionService
- ingestion/background_tasks.py: Background task runners
- ingestion/indexers/: Type-specific indexers

Import from app.services.ingestion_service (this module) for backward compatibility,
or directly from app.services.ingestion.* for explicit imports.
"""
# Re-export everything from the ingestion package
from app.services.ingestion import (
    # Main service
    IngestionService,
    # Types (dataclasses)
    SiteTreeNode,
    ScanResult,
    IndexingStatus,
    IndexingLogEntry,
    IndexingLogSummary,
    # Qdrant client
    get_qdrant_client,
    # Background tasks
    run_indexing_task,
    run_incremental_file_index_task,
    run_retry_task,
    run_selective_index_task,
)

__all__ = [
    "IngestionService",
    "SiteTreeNode",
    "ScanResult",
    "IndexingStatus",
    "IndexingLogEntry",
    "IndexingLogSummary",
    "get_qdrant_client",
    "run_indexing_task",
    "run_incremental_file_index_task",
    "run_retry_task",
    "run_selective_index_task",
]
