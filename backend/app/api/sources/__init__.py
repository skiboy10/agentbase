"""
Sources API - modular router structure.

This package provides API endpoints for source management,
indexing operations, and search functionality.
"""
from fastapi import APIRouter

from .sources import router as sources_router
from .indexing import router as indexing_router
from .operations import router as operations_router
from .watchers import router as watchers_router
from .analytics import router as analytics_router
from .stale import router as stale_router

# Aggregate all sub-routers into main sources router
# Operations router FIRST — static routes (/health, /search, /collections)
# must match before sources_router's /{source_id} wildcard
router = APIRouter()
router.include_router(operations_router)
router.include_router(analytics_router)
router.include_router(stale_router)
router.include_router(watchers_router)
router.include_router(sources_router)
router.include_router(indexing_router)

# Re-export schemas
from .schemas import (
    SourceCreate,
    SourceUpdate,
    SourceResponse,
    SearchRequest,
    SearchResult,
    ScanUrlRequest,
    ScanUrlResponse,
    SiteTreeNode,
    IndexingStatusResponse,
    IndexingLogResponse,
    IndexingLogsResponse,
    ProjectInfo,
    AdoptCollectionRequest,
    QdrantCollectionInfo,
)
