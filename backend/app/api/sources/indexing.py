"""
Knowledge indexing endpoints.

Handles indexing operations, status polling, logs, and refresh functionality.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import Scope, require_scope
from app.models import IndexingLog, APIKey
from app.services import IngestionService
from app.services.job_service import JobService

from .schemas import (
    SourceResponse,
    RefreshSourceRequest,
    IndexingStatusResponse,
    IndexingLogResponse,
    IndexingLogsResponse,
)
from .helpers import source_to_response

router = APIRouter()


# ==================== Indexing Operations ====================

@router.post("/{source_id}/index")
async def index_knowledge_source(
    source_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Trigger indexing of a knowledge source (runs in background via job queue).

    Query params:
        force: When True, override the "already_indexing" guard by marking any
            in-flight or queued index_source jobs as failed and re-enqueueing.
            Use to recover from stalled jobs (e.g., hung browser process).
    """
    service = IngestionService(db)

    try:
        status = await service.start_indexing(source_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if status == "already_indexing":
        return {
            "status": "indexing",
            "source_id": source_id,
            "message": "Indexing already in progress (pass force=true to re-trigger)",
        }

    # Enqueue job
    job_service = JobService(db)
    source = await service.get_source(source_id)
    job = await job_service.enqueue(
        "index_source",
        {"source_id": source_id},
        project_id=source.project_id if source else None,
    )
    await db.commit()

    return {
        "status": "indexing",
        "source_id": source_id,
        "job_id": job.id,
        "message": "Indexing started in background",
    }


@router.post("/{source_id}/retry-failed")
async def retry_failed_urls(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Retry indexing only failed URLs for a knowledge source."""
    service = IngestionService(db)

    try:
        status, retry_count = await service.retry_failed_urls(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if status == "already_indexing":
        return {
            "status": "indexing",
            "source_id": source_id,
            "message": "Indexing already in progress",
        }

    if status == "no_failures":
        return {
            "status": "no_failures",
            "source_id": source_id,
            "message": "No failed URLs to retry",
        }

    # Get the failed URLs to pass to job
    failed_logs = await service.get_indexing_logs(source_id, status_filter="pending")
    failed_urls = [log.url for log in failed_logs.logs]

    # Enqueue job
    job_service = JobService(db)
    source = await service.get_source(source_id)
    job = await job_service.enqueue(
        "retry_failed",
        {"source_id": source_id, "urls": failed_urls},
        project_id=source.project_id if source else None,
    )
    await db.commit()

    return {
        "status": "indexing",
        "source_id": source_id,
        "job_id": job.id,
        "message": f"Retrying {retry_count} failed URLs",
        "retry_count": retry_count,
    }


@router.post("/{source_id}/refresh")
async def refresh_knowledge_source(
    source_id: str,
    request: RefreshSourceRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Refresh a knowledge source.

    Modes:
    - full: Clear all documents and re-index everything
    - selective: Re-index only specified URLs (for URL sources)
    """
    service = IngestionService(db)
    job_service = JobService(db)

    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.source_type == "collection":
        raise HTTPException(
            status_code=400,
            detail="Cannot refresh an adopted Qdrant collection. The data is managed externally."
        )

    if source.status == "indexing" and not request.force:
        return {
            "status": "indexing",
            "source_id": source_id,
            "message": "Indexing already in progress (set force=true to re-trigger)",
        }

    if request.mode == "selective":
        if source.source_type != "url":
            raise HTTPException(
                status_code=400,
                detail="Selective refresh only available for URL sources"
            )
        if not request.urls:
            raise HTTPException(
                status_code=400,
                detail="Must specify URLs for selective refresh"
            )

        # Update indexing logs for selected URLs to pending
        update_stmt = update(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.url.in_(request.urls)
        ).values(
            status="pending",
            error_message=None,
            scrape_duration_ms=None,
            embed_duration_ms=None
        )
        await db.execute(update_stmt)

        # Start selective indexing via job queue
        await service.start_indexing(source_id, force=request.force)
        job = await job_service.enqueue(
            "selective_index",
            {"source_id": source_id, "urls": request.urls},
            project_id=source.project_id,
        )
        await db.commit()

        return {
            "status": "indexing",
            "source_id": source_id,
            "job_id": job.id,
            "message": f"Selective refresh started for {len(request.urls)} URLs",
            "mode": "selective",
            "url_count": len(request.urls),
        }

    # Full refresh mode via job queue
    await service.start_indexing(source_id, force=request.force)
    job = await job_service.enqueue(
        "index_source",
        {"source_id": source_id},
        project_id=source.project_id,
    )
    await db.commit()

    return {
        "status": "indexing",
        "source_id": source_id,
        "job_id": job.id,
        "message": "Full refresh started",
        "mode": "full",
    }


# ==================== Re-Enrichment ====================

@router.post("/{source_id}/re-enrich")
async def re_enrich_knowledge_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Re-classify all existing Qdrant chunks for a knowledge source using LLM enrichment.

    Requires the source to have a Qdrant collection (i.e. already indexed) and an
    enrichment taxonomy configured. Enqueues a background job that scrolls every
    chunk and updates its metadata payload with the classification result.

    Returns the job_id for tracking via GET /api/jobs/{job_id}.
    """
    service = IngestionService(db)
    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if not source.collection_name:
        raise HTTPException(
            status_code=400,
            detail="Source has no Qdrant collection. Index the source first before re-enriching.",
        )

    if not source.enrichment_taxonomy_id:
        raise HTTPException(
            status_code=400,
            detail="Source has no enrichment taxonomy configured. Set enrichment_taxonomy_id on the source.",
        )

    if source.status == "indexing":
        return {
            "status": "indexing",
            "source_id": source_id,
            "message": "Indexing or enrichment already in progress",
        }

    # Mark as indexing immediately to prevent duplicate jobs from concurrent requests.
    # The worker resets status to "indexed" (or "error") when it finishes.
    source.status = "indexing"
    source.error_message = None
    source.progress = 0
    source.progress_total = 0
    source.progress_message = "Re-enrichment queued"
    source.progress_updated_at = datetime.utcnow()

    job_service = JobService(db)
    job = await job_service.enqueue(
        "re_enrich_source",
        {"source_id": source_id},
        project_id=source.project_id,
    )
    await db.commit()

    return {
        "status": "queued",
        "source_id": source_id,
        "job_id": job.id,
        "message": "Re-enrichment job queued",
    }


# ==================== Indexing Status ====================

@router.get("/{source_id}/status", response_model=IndexingStatusResponse)
async def get_indexing_status(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get the current indexing status of a knowledge source."""
    service = IngestionService(db)

    try:
        status = await service.get_indexing_status(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return IndexingStatusResponse(
        source_id=status.source_id,
        status=status.status,
        progress=status.progress,
        progress_total=status.progress_total,
        progress_message=status.progress_message,
        progress_updated_at=None,  # Not in dataclass, could add if needed
        document_count=status.document_count,
        chunk_count=status.chunk_count,
        error_message=status.error_message,
    )


# ==================== Indexing Logs ====================

@router.get("/{source_id}/logs", response_model=IndexingLogsResponse)
async def get_indexing_logs(
    source_id: str,
    status_filter: Optional[str] = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get indexing logs for a knowledge source with summary stats."""
    service = IngestionService(db)

    try:
        summary = await service.get_indexing_logs(source_id, status_filter, limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return IndexingLogsResponse(
        logs=[
            IndexingLogResponse(
                id=log.id,
                source_id=log.source_id,
                url=log.url,
                status=log.status,
                error_message=log.error_message,
                scrape_duration_ms=log.scrape_duration_ms,
                embed_duration_ms=log.embed_duration_ms,
                content_length=log.content_length,
                chunk_count=log.chunk_count,
                created_at=log.created_at,
                updated_at=log.updated_at,
            )
            for log in summary.logs
        ],
        summary={
            "total": summary.total,
            "done": summary.done,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "pending": summary.pending,
            "in_progress": summary.in_progress,
        },
    )


@router.delete("/{source_id}/logs", status_code=204)
async def clear_indexing_logs(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Clear all indexing logs for a knowledge source."""
    service = IngestionService(db)

    try:
        await service.clear_indexing_logs(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return None
