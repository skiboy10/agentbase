"""
Job queue API endpoints.

Provides visibility into background job status, cancellation, and retry.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services.job_service import JobService

router = APIRouter()


class JobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    priority: int
    payload: dict
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    max_retries: int
    project_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _job_to_response(job) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "priority": job.priority,
        "payload": job.payload,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "project_id": job.project_id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("/")
async def list_jobs(
    job_type: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List jobs with optional filters."""
    service = JobService(db)
    jobs = await service.list_jobs(
        job_type=job_type,
        status=status,
        project_id=project_id,
        limit=min(limit, 200),
        offset=offset,
    )
    return [_job_to_response(j) for j in jobs]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a single job by ID."""
    service = JobService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Cancel a queued or running job."""
    service = JobService(db)
    cancelled = await service.cancel(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=400,
            detail="Job cannot be cancelled (not found or not in queued/running state)"
        )
    return {"status": "cancelled", "job_id": job_id}


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Re-enqueue a failed job."""
    service = JobService(db)
    retried = await service.retry(job_id)
    if not retried:
        raise HTTPException(
            status_code=400,
            detail="Job cannot be retried (not found or not in failed state)"
        )
    return {"status": "queued", "job_id": job_id}
