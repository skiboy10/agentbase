"""
Knowledge operations endpoints.

Handles URL scanning, search, collections listing, and health checks.
"""
import asyncio
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.auth import Scope, require_scope
from app.core.url_validator import validate_url
from app.models import Source, APIKey
from app.services import IngestionService, RAGService
from app.services.rag.client import get_qdrant_client
from app.services.rag.neighbors import fetch_chunk_neighbors

logger = structlog.get_logger()

from .schemas import (
    ScanUrlRequest,
    ScanUrlResponse,
    SearchRequest,
    SearchResult,
    DeepSearchRequest,
    DeepSearchResponse,
    QdrantCollectionInfo,
)
from .helpers import tree_to_response

router = APIRouter()
settings = get_settings()


# ==================== URL Scanning ====================

@router.post("/scan-url", response_model=ScanUrlResponse)
async def scan_url_structure(
    request: ScanUrlRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Stage 1: Scan a URL and return the site tree structure.

    Three modes:
    1. Auto-discover mode: If auto_discover_sitemap=True, discovers sitemap automatically
    2. Sitemap mode: If sitemap_url is provided, fetches URLs from sitemap
    3. Crawl mode (fallback): Crawls the given URL, discovers linked pages
    """
    # Validate URL before any server-side fetching (SSRF protection)
    try:
        validate_url(request.url)
        if request.sitemap_url:
            validate_url(request.sitemap_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    service = IngestionService(db)

    try:
        result = await service.scan_url(
            url=request.url,
            max_depth=request.max_depth,
            path_scope=request.path_scope,
            sitemap_url=request.sitemap_url,
            path_filter=request.path_filter,
            auto_discover_sitemap=request.auto_discover_sitemap,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan URL: {str(e)}")

    return ScanUrlResponse(
        tree=tree_to_response(result.tree),
        sitemap_url=result.sitemap_url,
    )


# ==================== Search ====================

@router.post("/search", response_model=list[SearchResult])
async def search_knowledge(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    Search the knowledge base.

    By default uses hybrid search combining semantic similarity and keyword matching.
    Set hybrid=false for pure semantic search.
    """
    rag_service = RAGService(db)

    try:
        if request.hybrid:
            results = await rag_service.search_hybrid(
                query=request.query,
                project_id=request.project_id,
                top_k=request.top_k,
                vector_weight=request.vector_weight,
                filters=request.filters,
                source_ids=request.source_ids,
                knowledge_base_id=request.knowledge_base_id,
                rerank=request.rerank,
            )
        else:
            results = await rag_service.search(
                query=request.query,
                project_id=request.project_id,
                top_k=request.top_k,
                source_ids=request.source_ids,
                filters=request.filters,
                knowledge_base_id=request.knowledge_base_id,
                rerank=request.rerank,
            )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    # Fetch neighboring chunks in parallel when requested
    neighbor_lists: list[list[dict] | None] = [None] * len(results)
    if request.include_neighbors > 0 and results:
        client = get_qdrant_client()

        async def _fetch(idx: int, r) -> tuple[int, list[dict] | None]:
            try:
                chunks = await fetch_chunk_neighbors(
                    client=client,
                    collection=r.collection,
                    metadata=r.metadata,
                    chunk_index=r.metadata.get("chunk_index"),
                    window_size=request.include_neighbors,
                )
                return idx, chunks
            except Exception as exc:
                logger.warning(
                    "REST: fetch_chunk_neighbors failed for result",
                    collection=r.collection,
                    chunk_index=r.metadata.get("chunk_index"),
                    error=str(exc),
                )
                return idx, None

        fetched = await asyncio.gather(*[_fetch(i, r) for i, r in enumerate(results)])
        for idx, chunks in fetched:
            neighbor_lists[idx] = chunks

    return [
        SearchResult(
            content=r.content,
            source=r.source,
            score=r.score,
            title=r.title,
            source_name=r.source_name,
            document_path=r.document_path,
            collection=r.collection,
            rerank_score=r.rerank_score,
            metadata=r.metadata,
            context_chunks=neighbor_lists[i],
        )
        for i, r in enumerate(results)
    ]


# ==================== Deep Search ====================

@router.post("/deep-search", response_model=DeepSearchResponse)
async def deep_search(
    request: DeepSearchRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    Deep search with automatic query decomposition.

    Breaks a complex query into focused sub-queries, searches each in
    parallel, deduplicates, fuses via RRF, and reranks against the
    original query. Best for multi-part questions spanning multiple
    entities or aspects.
    """
    rag_service = RAGService(db)

    try:
        result = await rag_service.deep_search(
            query=request.query,
            top_k=request.top_k,
            max_sub_queries=request.max_sub_queries,
            filters=request.filters,
            source_ids=request.source_ids,
            knowledge_base_id=request.knowledge_base_id,
            rerank=request.rerank,
            include_decomposition=request.include_decomposition,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep search failed: {str(e)}")

    return DeepSearchResponse(
        results=[
            SearchResult(
                content=r.content,
                source=r.source,
                score=r.score,
                title=r.title,
                source_name=r.source_name,
                document_path=r.document_path,
                collection=r.collection,
                rerank_score=r.rerank_score,
                metadata=r.metadata,
            )
            for r in result.results
        ],
        sub_queries=[
            {"query": sq.query, "filters": sq.filters, "strategy": sq.strategy}
            for sq in result.sub_queries
        ],
        stats=result.stats,
    )


# ==================== Collections ====================

@router.get("/collections")
async def list_qdrant_collections(
    include_details: bool = False,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    List Qdrant collections.

    If include_details=True, returns detailed info including vector counts
    and whether the collection is linked to a knowledge source.
    """
    from app.services.ingestion_service import get_qdrant_client
    import structlog

    logger = structlog.get_logger()

    try:
        client = get_qdrant_client()
        collections = client.get_collections()

        if not include_details:
            return {
                "collections": [
                    {"name": c.name}
                    for c in collections.collections
                ]
            }

        # Get all knowledge sources to check linkage
        stmt = select(Source)
        result = await db.execute(stmt)
        sources = result.scalars().all()
        source_by_collection = {s.collection_name: s for s in sources if s.collection_name}

        detailed_collections = []
        for c in collections.collections:
            try:
                info = client.get_collection(c.name)
                vector_config = info.config.params.vectors

                # Handle both named vectors and single vector config
                vector_size = None
                distance = None
                if hasattr(vector_config, 'size'):
                    vector_size = vector_config.size
                    distance = str(vector_config.distance) if hasattr(vector_config, 'distance') else None
                elif isinstance(vector_config, dict) and 'size' in vector_config:
                    vector_size = vector_config['size']
                    distance = str(vector_config.get('distance', ''))

                linked_source = source_by_collection.get(c.name)

                detailed_collections.append(QdrantCollectionInfo(
                    name=c.name,
                    vectors_count=info.points_count or 0,  # vectors_count deprecated in Qdrant client
                    points_count=info.points_count or 0,
                    vector_size=vector_size,
                    distance=distance,
                    is_linked=linked_source is not None,
                    linked_source_id=linked_source.id if linked_source else None,
                    linked_source_name=linked_source.name if linked_source else None,
                ))
            except Exception as e:
                logger.warning("Failed to get collection details", collection=c.name, error=str(e))
                detailed_collections.append(QdrantCollectionInfo(
                    name=c.name,
                    vectors_count=0,
                    points_count=0,
                ))

        return {"collections": [c.model_dump() for c in detailed_collections]}

    except Exception as e:
        logger.error("Failed to list Qdrant collections", error=str(e))
        raise HTTPException(status_code=503, detail=f"Qdrant connection error: {str(e)}")


# ==================== Health ====================

@router.get("/health")
async def knowledge_health(
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Check health of knowledge base components."""
    from app.services.ingestion_service import get_qdrant_client

    qdrant_healthy = False
    qdrant_message = ""

    try:
        client = get_qdrant_client()
        collections = client.get_collections()
        qdrant_healthy = True
        qdrant_message = f"Connected, {len(collections.collections)} collections"
    except Exception as e:
        qdrant_message = str(e)

    return {
        "qdrant": {
            "healthy": qdrant_healthy,
            "message": qdrant_message,
            "url": settings.qdrant_url,
        }
    }
