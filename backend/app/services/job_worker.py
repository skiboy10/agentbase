"""
Background job worker loop.

Polls for queued jobs and executes handlers. Started in the FastAPI lifespan.
"""
import asyncio
from typing import Callable

import structlog

from app.core.database import async_session_maker
from app.services.job_service import JobService

logger = structlog.get_logger()

# Poll interval in seconds when no jobs are available
POLL_INTERVAL = 2


async def job_worker_loop(handler_map: dict[str, Callable]) -> None:
    """
    Continuously poll for queued jobs and execute them.

    Each handler receives the job payload dict and must manage its own
    database session for the actual work.
    """
    job_types = list(handler_map.keys())
    logger.info("Job worker started", job_types=job_types)

    while True:
        try:
            # Dequeue in its own session (short-lived)
            async with async_session_maker() as db:
                service = JobService(db)
                job = await service.dequeue(job_types)

            if job is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Execute the handler
            handler = handler_map.get(job.job_type)
            if not handler:
                async with async_session_maker() as db:
                    service = JobService(db)
                    await service.fail(job.id, f"Unknown job type: {job.job_type}")
                continue

            try:
                await handler(job.payload)
                # Mark complete in its own session
                async with async_session_maker() as db:
                    service = JobService(db)
                    await service.complete(job.id)
            except Exception as e:
                logger.exception("Job execution failed", job_id=job.id, job_type=job.job_type)
                async with async_session_maker() as db:
                    service = JobService(db)
                    await service.fail(job.id, str(e))

        except asyncio.CancelledError:
            logger.info("Job worker shutting down")
            break
        except Exception as e:
            # Don't let worker loop crash on unexpected errors
            logger.error("Job worker loop error", error=str(e))
            await asyncio.sleep(POLL_INTERVAL)
