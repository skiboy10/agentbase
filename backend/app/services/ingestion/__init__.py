"""
Ingestion service package.

This package handles document ingestion, indexing, and URL scanning.

The package has been split into focused modules:
- types.py: Data classes (SiteTreeNode, ScanResult, IndexingStatus, etc.)
- qdrant_client.py: Qdrant client singleton
- embedding_processor.py: Shared embedding and Qdrant operations
- source_manager.py: Source CRUD operations
- log_manager.py: Indexing log operations
- url_scanner.py: URL structure scanning
- orchestrator.py: Main IngestionService that coordinates everything
- background_tasks.py: Background task runners
- indexers/: Type-specific indexers (directory, file, URL)
- text_cleaner.py: PDF artifact removal + presentation detection
- enrichment.py: LLM classification pipeline (EnrichmentService, EnrichmentConfig)

For backward compatibility, import from this package:
    from app.services.ingestion import IngestionService, run_indexing_task
"""
# Main service
from .orchestrator import IngestionService

# Types (dataclasses)
from .types import (
    SiteTreeNode,
    ScanResult,
    IndexingStatus,
    IndexingLogEntry,
    IndexingLogSummary,
)

# Qdrant client (from both locations for compatibility)
from .qdrant_client import get_qdrant_client

# Embedding processor (keep existing)
from .embedding_processor import EmbeddingProcessor

# Background tasks
from .background_tasks import (
    reindex_file,
    run_indexing_task,
    run_incremental_file_index_task,
    run_retry_task,
    run_selective_index_task,
)

# Component managers (for direct access if needed)
from .source_manager import SourceManager
from .log_manager import LogManager
from .url_scanner import UrlScanner
from .queue_manager import QueueManager
from .document_ops import DocumentOps

# Indexers
from .indexers import (
    BaseIndexer,
    DirectoryIndexer,
    FileIndexer,
    FileItemIndexer,
    UrlIndexer,
)

# Enrichment pipeline
from .enrichment import EnrichmentService, EnrichmentConfig
from .text_cleaner import clean_text

# Directory watcher
from .watcher import WatcherManager, DirectoryWatcher, watcher_manager

__all__ = [
    # Main service
    "IngestionService",
    # Types
    "SiteTreeNode",
    "ScanResult",
    "IndexingStatus",
    "IndexingLogEntry",
    "IndexingLogSummary",
    # Qdrant & Embedding
    "get_qdrant_client",
    "EmbeddingProcessor",
    # Background tasks
    "reindex_file",
    "run_indexing_task",
    "run_incremental_file_index_task",
    "run_retry_task",
    "run_selective_index_task",
    # Managers
    "SourceManager",
    "LogManager",
    "UrlScanner",
    "QueueManager",
    "DocumentOps",
    # Indexers
    "BaseIndexer",
    "DirectoryIndexer",
    "FileIndexer",
    "FileItemIndexer",
    "UrlIndexer",
    # Enrichment
    "EnrichmentService",
    "EnrichmentConfig",
    "clean_text",
    # Watcher
    "WatcherManager",
    "DirectoryWatcher",
    "watcher_manager",
]
