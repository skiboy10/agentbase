"""
Maintenance scheduler — background task that periodically enqueues
housekeeping jobs (currently watcher-event garbage collection).

Simple asyncio polling loop, mirroring ``refresh_scheduler``. Runs every
``watcher_events_gc_interval_hours`` (default 24). No cron, no APScheduler.

This replaces the previous startup-only GC enqueue: a long-running backend
must keep pruning, otherwise a chatty directory watcher accumulates millions
of ``watcher_events`` rows between restarts.
"""
import asyncio

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.models import Job
from app.services.job_service import JobService

logger = structlog.get_logger()


async def _enqueue_watcher_gc() -> None:
    """Enqueue a watcher_events_gc job unless one is already pending/running.

    Dedup avoids stacking GC jobs across rapid restarts or (future) multiple
    replicas — a single backlog-clearing run is all that's needed per cycle.
    """
    async with async_session_maker() as db:
        existing = await db.execute(
            select(Job.id).where(
                Job.job_type == "watcher_events_gc",
                Job.status.in_(["queued", "running"]),
            ).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            logger.debug("Maintenance scheduler: GC job already pending, skipping enqueue")
            return
        await JobService(db).enqueue("watcher_events_gc", {})
        await db.commit()


async def maintenance_scheduler_loop() -> None:
    """Background loop that periodically enqueues watcher-event GC.

    Enqueues once immediately on startup, then every
    ``watcher_events_gc_interval_hours``. Runs until cancelled; catches all
    exceptions so a transient error never kills the loop.
    """
    settings = get_settings()
    interval_seconds = settings.watcher_events_gc_interval_hours * 3600

    logger.info(
        "Maintenance scheduler started",
        gc_interval_hours=settings.watcher_events_gc_interval_hours,
    )

    # Prime once at startup, then settle into the interval.
    try:
        await _enqueue_watcher_gc()
    except Exception:
        logger.exception("Maintenance scheduler: initial GC enqueue failed")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await _enqueue_watcher_gc()
            logger.info("Maintenance scheduler: enqueued watcher_events_gc")
        except asyncio.CancelledError:
            logger.info("Maintenance scheduler stopped")
            raise
        except Exception:
            logger.exception("Maintenance scheduler error (will retry next cycle)")
