"""
Knowledge analytics endpoint.

Provides a bird's-eye view of the entire knowledge base: source counts, chunk
totals, embedding model distribution, classification coverage, and Qdrant
storage stats. All DB work uses SQL aggregates — no full table scans in Python.
"""
import structlog
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import Scope, require_scope
from app.models import Source, Library, DocumentContent, Document, APIKey
from app.services.ingestion.watcher import watcher_manager

logger = structlog.get_logger()

router = APIRouter()


@router.get("/analytics")
async def get_knowledge_analytics(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    Return comprehensive statistics about the knowledge system.

    Queries are SQL-aggregate based for speed. Qdrant point counts come from
    the Qdrant API. Classification coverage is estimated from a 100-point
    sample per collection rather than a full scan.
    """

    # ------------------------------------------------------------------
    # 1. Core source aggregates (single query)
    # ------------------------------------------------------------------
    agg_stmt = select(
        func.count(Source.id).label("total_sources"),
        func.sum(
            case((Source.status == "indexed", 1), else_=0)
        ).label("indexed_sources"),
        func.sum(Source.document_count).label("total_documents"),
        func.sum(Source.chunk_count).label("total_chunks"),
        func.sum(
            case((Source.enrichment_enabled.is_(True), 1), else_=0)
        ).label("sources_with_enrichment"),
    )
    agg_result = await db.execute(agg_stmt)
    agg_row = agg_result.one()

    total_sources: int = int(agg_row.total_sources or 0)
    indexed_sources: int = int(agg_row.indexed_sources or 0)
    total_documents: int = int(agg_row.total_documents or 0)
    total_chunks: int = int(agg_row.total_chunks or 0)
    sources_with_enrichment: int = int(agg_row.sources_with_enrichment or 0)

    # ------------------------------------------------------------------
    # 2. Sources by type
    # ------------------------------------------------------------------
    type_stmt = select(
        Source.source_type,
        func.count(Source.id).label("cnt"),
    ).group_by(Source.source_type)
    type_result = await db.execute(type_stmt)
    sources_by_type: dict[str, int] = {
        row.source_type: row.cnt for row in type_result.all()
    }

    # ------------------------------------------------------------------
    # 3. Sources by status
    # ------------------------------------------------------------------
    status_stmt = select(
        Source.status,
        func.count(Source.id).label("cnt"),
    ).group_by(Source.status)
    status_result = await db.execute(status_stmt)
    sources_by_status: dict[str, int] = {
        row.status: row.cnt for row in status_result.all()
    }

    # ------------------------------------------------------------------
    # 4. Top sources by chunk count (top 10)
    # ------------------------------------------------------------------
    top_stmt = (
        select(
            Source.name,
            Source.chunk_count,
            Source.document_count,
        )
        .order_by(Source.chunk_count.desc())
        .limit(10)
    )
    top_result = await db.execute(top_stmt)
    top_sources = [
        {
            "name": row.name,
            "chunks": row.chunk_count,
            "documents": row.document_count,
        }
        for row in top_result.all()
    ]

    # ------------------------------------------------------------------
    # 5. Embedding model distribution
    # ------------------------------------------------------------------
    emb_stmt = select(
        Source.embedding_provider,
        Source.embedding_model,
        func.count(Source.id).label("cnt"),
    ).where(
        Source.embedding_model.isnot(None)
    ).group_by(
        Source.embedding_provider,
        Source.embedding_model,
    )
    emb_result = await db.execute(emb_stmt)
    embedding_models: dict[str, int] = {}
    for row in emb_result.all():
        provider = row.embedding_provider or ""
        model = row.embedding_model or ""
        key = f"{provider}/{model}" if provider else model
        embedding_models[key] = row.cnt

    # ------------------------------------------------------------------
    # 6. Library count
    # ------------------------------------------------------------------
    kb_stmt = select(func.count(Library.id))
    kb_result = await db.execute(kb_stmt)
    libraries: int = int(kb_result.scalar() or 0)

    # ------------------------------------------------------------------
    # 7. Active watcher count (in-memory singleton — no DB needed)
    # ------------------------------------------------------------------
    try:
        active_watchers: int = len(watcher_manager.get_all_statuses())
    except Exception:
        active_watchers = 0

    # ------------------------------------------------------------------
    # 8. Qdrant: collection count + total points
    # ------------------------------------------------------------------
    total_qdrant_points = 0
    qdrant_collections = 0
    try:
        from app.services.ingestion_service import get_qdrant_client

        client = get_qdrant_client()
        collections_response = client.get_collections()
        qdrant_collections = len(collections_response.collections)

        for col in collections_response.collections:
            try:
                info = client.get_collection(col.name)
                total_qdrant_points += info.points_count or 0
            except Exception as col_err:
                logger.warning(
                    "Could not get collection info",
                    collection=col.name,
                    error=str(col_err),
                )
    except Exception as qdrant_err:
        logger.warning("Qdrant unavailable for analytics", error=str(qdrant_err))

    # ------------------------------------------------------------------
    # 9. Classification coverage
    #    Sum chunk_count from Document rows that have a non-null
    #    classification (written by the enrichment pipeline). Denominator
    #    is the already-computed total_chunks (sum of Source.chunk_count).
    # ------------------------------------------------------------------
    classified_chunks = 0
    classification_total_chunks = total_chunks  # reuse the already-computed total

    try:
        # Sum chunk counts for documents with a non-null classification
        classified_stmt = select(
            func.sum(Document.chunk_count)
        ).where(
            Document.classification.isnot(None)
        )
        classified_result = await db.execute(classified_stmt)
        classified_chunks = int(classified_result.scalar() or 0)
    except Exception as cov_err:
        logger.warning("Classification coverage query failed", error=str(cov_err))

    coverage_percent = (
        round((classified_chunks / classification_total_chunks) * 100, 1)
        if classification_total_chunks > 0
        else 0.0
    )

    # ------------------------------------------------------------------
    # Compose response
    # ------------------------------------------------------------------
    return {
        "summary": {
            "total_sources": total_sources,
            "indexed_sources": indexed_sources,
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_qdrant_points": total_qdrant_points,
            "libraries": libraries,
            "active_watchers": active_watchers,
            "sources_with_enrichment": sources_with_enrichment,
        },
        "sources_by_type": sources_by_type,
        "sources_by_status": sources_by_status,
        "top_sources": top_sources,
        "embedding_models": embedding_models,
        "classification_coverage": {
            "classified_chunks": classified_chunks,
            "total_chunks": classification_total_chunks,
            "coverage_percent": coverage_percent,
        },
        "storage": {
            "qdrant_collections": qdrant_collections,
            "total_qdrant_points": total_qdrant_points,
        },
    }
