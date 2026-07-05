"""
Refresh scheduler — background task that checks for automatic-policy
sources due for re-indexing and enqueues indexing jobs.

V1: simple asyncio polling loop. Runs every REFRESH_CHECK_INTERVAL_MINUTES
(default 60). No cron, no APScheduler, no Celery.
"""
import asyncio
from datetime import datetime

import structlog

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.models import Source, Job
from app.services.job_service import JobService

from sqlalchemy import select, and_

logger = structlog.get_logger()


async def _check_and_enqueue_refreshes() -> int:
    """Scan for automatic sources due for refresh and enqueue jobs.

    All due sources are enqueued — the single-threaded job worker drains the
    queue serially, so queue depth alone does not cause concurrent execution.
    Per-job memory pressure is bounded by the Playwright semaphore
    (``MAX_CONCURRENT`` in ``web_scraper.types``).

    Returns the number of refresh jobs enqueued.
    """
    now = datetime.utcnow()
    enqueued = 0

    async with async_session_maker() as db:
        # Find automatic sources whose next_refresh_at has passed.
        # Oldest-due first so a long-stalled source isn't starved by newer ones.
        stmt = select(Source).where(
            and_(
                Source.freshness_policy == "automatic",
                Source.next_refresh_at.isnot(None),
                Source.next_refresh_at <= now,
                Source.status != "indexing",  # Don't re-queue if already indexing
            )
        ).order_by(Source.next_refresh_at.asc())
        result = await db.execute(stmt)
        due_sources = result.scalars().all()

        if not due_sources:
            return 0

        job_svc = JobService(db)

        for source in due_sources:
            # Check no pending/running index job already exists
            existing_stmt = select(Job).where(
                and_(
                    Job.job_type == "index_source",
                    Job.status.in_(["queued", "running"]),
                    Job.payload["source_id"].as_string() == source.id,
                )
            )
            existing_result = await db.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                logger.debug(
                    "Refresh scheduler: skipping (job already queued)",
                    source_id=source.id,
                    source_name=source.name,
                )
                continue

            await job_svc.enqueue(
                job_type="index_source",
                payload={"source_id": source.id},
                priority=0,
                project_id=source.project_id,
            )
            enqueued += 1
            logger.info(
                "Refresh scheduler: enqueued re-index",
                source_id=source.id,
                source_name=source.name,
                next_refresh_at=source.next_refresh_at.isoformat() if source.next_refresh_at else None,
            )

        await db.commit()

    return enqueued


async def refresh_scheduler_loop() -> None:
    """Background loop that periodically checks for due automatic refreshes.

    Runs indefinitely until cancelled. Catches all exceptions to avoid
    crashing the scheduler on transient errors.
    """
    settings = get_settings()
    interval_seconds = settings.refresh_check_interval_minutes * 60

    logger.info(
        "Refresh scheduler started",
        check_interval_minutes=settings.refresh_check_interval_minutes,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            enqueued = await _check_and_enqueue_refreshes()
            if enqueued > 0:
                logger.info("Refresh scheduler cycle complete", enqueued=enqueued)
        except asyncio.CancelledError:
            logger.info("Refresh scheduler stopped")
            raise
        except Exception:
            logger.exception("Refresh scheduler error (will retry next cycle)")
