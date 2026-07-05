"""Business logic services."""

from app.services.rag import RAGService, RAGContext, RAGSource, SearchResult, reciprocal_rank_fusion, weighted_rrf, get_qdrant_client
from app.services.provider_service import ProviderService, ProviderStatus, ModelAssignmentInfo
from app.services.ingestion_service import (
    IngestionService,
    ScanResult,
    SiteTreeNode,
    IndexingStatus,
    IndexingLogEntry,
    IndexingLogSummary,
    run_indexing_task,
    run_incremental_file_index_task,
    run_retry_task,
    run_selective_index_task,
)
from app.services.prompt_service import PromptService
from app.services.agent_service import AgentService, AgentInfo
from app.services.library import LibraryService, KnowledgeBaseService, DocumentService
from app.services.agent_query import AgentQueryService

__all__ = [
    # RAG Service
    "RAGService",
    "RAGContext",
    "RAGSource",
    "SearchResult",
    "reciprocal_rank_fusion",
    "weighted_rrf",
    "get_qdrant_client",
    # Provider Service
    "ProviderService",
    "ProviderStatus",
    "ModelAssignmentInfo",
    # Ingestion Service
    "IngestionService",
    "ScanResult",
    "SiteTreeNode",
    "IndexingStatus",
    "IndexingLogEntry",
    "IndexingLogSummary",
    "run_indexing_task",
    "run_incremental_file_index_task",
    "run_retry_task",
    "run_selective_index_task",
    # Prompt Service
    "PromptService",
    # Agent Service
    "AgentService",
    "AgentInfo",
    # Library Service
    "LibraryService",
    "KnowledgeBaseService",
    "DocumentService",
    # Agent Query Service
    "AgentQueryService",
]
