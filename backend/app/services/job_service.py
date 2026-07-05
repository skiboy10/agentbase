"""
Database-backed job queue service.

Provides persistent job enqueuing, dequeuing with SKIP LOCKED,
retry logic, and status management.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Job

logger = structlog.get_logger()


class JobService:
    """Manages the persistent job queue."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue(
        self,
        job_type: str,
        payload: dict,
        priority: int = 0,
        project_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> Job:
        """Create a new job with status 'queued'."""
        job = Job(
            job_type=job_type,
            payload=payload,
            priority=priority,
            project_id=project_id,
            max_retries=max_retries,
        )
        self.db.add(job)
        await self.db.flush()  # Get the ID without committing
        logger.info("Job enqueued", job_id=job.id, job_type=job_type)
        return job

    async def dequeue(self, job_types: list[str]) -> Optional[Job]:
        """Atomically claim the next queued job using SELECT FOR UPDATE SKIP LOCKED."""
        stmt = (
            select(Job)
            .where(Job.status == "queued", Job.job_type.in_(job_types))
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = "running"
            job.started_at = datetime.utcnow()
            await self.db.commit()
            logger.info("Job dequeued", job_id=job.id, job_type=job.job_type)
        return job

    async def complete(self, job_id: str) -> None:
        """Mark a job as completed (only if still running)."""
        stmt = select(Job).where(Job.id == job_id, Job.status == "running")
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.info("Job completed", job_id=job_id, job_type=job.job_type)

    async def fail(self, job_id: str, error_message: str) -> None:
        """Mark a job as failed. Re-queues if under max_retries. Only acts on running jobs."""
        stmt = select(Job).where(Job.id == job_id, Job.status == "running")
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return

        job.retry_count += 1
        job.error_message = error_message

        if job.retry_count < job.max_retries:
            job.status = "queued"
            job.started_at = None
            logger.warning(
                "Job failed, re-queued",
                job_id=job_id, job_type=job.job_type,
                retry=job.retry_count, max_retries=job.max_retries,
                error=error_message[:200],
            )
        else:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            logger.error(
                "Job failed permanently",
                job_id=job_id, job_type=job.job_type,
                retries=job.retry_count,
                error=error_message[:200],
            )

        await self.db.commit()

    async def cancel(self, job_id: str) -> bool:
        """Cancel a queued or running job. Returns True if cancelled."""
        stmt = select(Job).where(Job.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job or job.status not in ("queued", "running"):
            return False

        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        await self.db.commit()
        logger.info("Job cancelled", job_id=job_id, job_type=job.job_type)
        return True

    async def retry(self, job_id: str) -> bool:
        """Re-enqueue a failed job. Returns True if re-queued."""
        stmt = select(Job).where(Job.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job or job.status != "failed":
            return False

        job.status = "queued"
        job.retry_count = 0
        job.started_at = None
        job.completed_at = None
        job.error_message = None
        await self.db.commit()
        logger.info("Job re-queued", job_id=job_id, job_type=job.job_type)
        return True

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a single job by ID."""
        stmt = select(Job).where(Job.id == job_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        job_type: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """List jobs with optional filters."""
        stmt = select(Job).order_by(Job.created_at.desc())

        if job_type:
            stmt = stmt.where(Job.job_type == job_type)
        if status:
            stmt = stmt.where(Job.status == status)
        if project_id:
            stmt = stmt.where(Job.project_id == project_id)

        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def recover_stale_jobs(self, timeout_minutes: int = 30) -> int:
        """Re-queue jobs stuck in 'running' for too long (e.g., after a crash)."""
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        stmt = (
            update(Job)
            .where(
                Job.status == "running",
                Job.started_at < cutoff,
            )
            .values(status="queued", started_at=None)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        count = result.rowcount
        if count:
            logger.warning("Recovered stale jobs", count=count, timeout_minutes=timeout_minutes)
        return count
