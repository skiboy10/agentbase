"""
Background task runners for indexing operations.

These functions run in background threads/tasks and manage their own database sessions.
"""

import asyncio
from datetime import datetime

from sqlalchemy import select
import structlog

from app.core.database import async_session_maker
from app.core.events import publish_source_event
from app.models import Source

logger = structlog.get_logger()


# Bound how many per-file re-index tasks run at once. force_sync and the watcher
# poll loop can dispatch thousands of reindex_file tasks via asyncio.create_task;
# without a cap they each grab a DB session and exhaust the connection pool
# ("QueuePool limit ... connection timed out"). A small cap keeps DB usage well
# under the pool while staying productive; excess tasks queue on the semaphore.
REINDEX_MAX_CONCURRENCY = 5
_reindex_semaphore = asyncio.Semaphore(REINDEX_MAX_CONCURRENCY)


async def emit_source_indexed_event(db, source_id: str) -> None:
    """Fetch the fresh source row and publish a source.indexed SSE event.

    Call after a successful indexing run has committed. Failures are
    swallowed — observability must never break the indexing pipeline.
    """
    try:
        stmt = select(Source).where(Source.id == source_id)
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if source:
            await publish_source_event(
                "indexed",
                source_id,
                {
                    "name": source.name,
                    "chunk_count": source.chunk_count or 0,
                    "document_count": source.document_count or 0,
                    "status": source.status,
                },
            )
    except Exception as evt_e:
        logger.warning("Failed to emit source.indexed event", source_id=source_id, error=str(evt_e))


async def record_source_failure(db, source_id: str, error: Exception, progress_message: str | None = None) -> None:
    """Roll back, mark the source as errored, commit, and publish source.failed.

    Rolls back first so the (likely aborted) transaction doesn't raise
    PendingRollbackError on the status-update query. Captures source.name
    before commit since commit expires ORM instances in async sessions.
    """
    try:
        await db.rollback()
        stmt = select(Source).where(Source.id == source_id)
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if source:
            source_name = source.name  # capture before commit expires the instance
            source.status = "error"
            source.error_message = str(error)
            if progress_message is not None:
                source.progress_message = progress_message
            source.progress_updated_at = datetime.utcnow()
            await db.commit()
            try:
                await publish_source_event(
                    "failed",
                    source_id,
                    {"name": source_name, "error": str(error)},
                )
            except Exception as evt_e:
                logger.warning("Failed to emit source.failed event", source_id=source_id, error=str(evt_e))
    except Exception as inner_e:
        logger.error("Failed to update error status", source_id=source_id, error=str(inner_e))


async def _process_next_queued(db):
    """Process the next queued source if a slot is available."""
    from .queue_manager import QueueManager

    try:
        queue_manager = QueueManager(db)
        if await queue_manager.can_start_indexing():
            next_id = await queue_manager.get_next_queued()
            if next_id:
                stmt = select(Source).where(Source.id == next_id)
                result = await db.execute(stmt)
                next_source = result.scalar_one_or_none()
                if next_source:
                    next_source.status = "indexing"
                    await db.commit()
                    logger.info("Starting next queued source", source_id=next_id)
                    asyncio.create_task(run_indexing_task(next_id))
    except Exception as qe:
        logger.error("Failed to process queue", error=str(qe))


async def run_indexing_task(source_id: str):
    """Background task to run indexing with its own database session."""
    from .orchestrator import IngestionService

    logger.info("Background indexing task started", source_id=source_id)
    async with async_session_maker() as db:
        try:
            service = IngestionService(db)
            await service.execute_indexing(source_id)
            await db.commit()
            logger.info("Background indexing task completed", source_id=source_id)
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Background indexing failed", source_id=source_id, error=str(e), exc_info=True)
            await record_source_failure(db, source_id, e, f"Failed: {str(e)}")
        finally:
            # Always try to process next queued source
            await _process_next_queued(db)


async def reindex_file(source_id: str, file_path: str) -> None:
    """Background task: re-index a single file under a directory source.

    Used by the directory watcher in response to a file event. Skips quietly
    when the file is unchanged, unsupported, missing, or outside the source
    root. Hard errors are logged and surface as a watcher "error" event via
    the caller's own retry/event-emission paths.

    Concurrency is bounded by ``_reindex_semaphore`` so a large fan-out (e.g.
    force_sync over thousands of files) can't exhaust the DB connection pool.
    """
    async with _reindex_semaphore:
        await _reindex_file_inner(source_id, file_path)


async def _reindex_file_inner(source_id: str, file_path: str) -> None:
    from .indexers.file_item import FileItemIndexer

    logger.info("Per-file re-index task started", source_id=source_id, file=file_path)
    async with async_session_maker() as db:
        try:
            stmt = select(Source).where(Source.id == source_id)
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()
            if source is None:
                logger.warning("Source not found for per-file re-index", source_id=source_id)
                return

            indexer = FileItemIndexer(db)
            indexer._load_source_metadata(source)
            stats = await indexer.index_one(source, file_path)
            await db.commit()
            logger.info(
                "Per-file re-index task completed",
                source_id=source_id,
                file=file_path,
                stats=stats,
            )
        except Exception as e:
            logger.error(
                "Per-file re-index failed",
                source_id=source_id,
                file=file_path,
                error=str(e),
                exc_info=True,
            )
            try:
                await db.rollback()
            except Exception:
                pass


async def run_incremental_file_index_task(source_id: str, new_files: list[dict]):
    """Background task to index only newly added files."""
    from .orchestrator import IngestionService

    logger.info("Incremental file indexing task started", source_id=source_id, file_count=len(new_files))
    async with async_session_maker() as db:
        try:
            service = IngestionService(db)
            await service.execute_incremental_file_indexing(source_id, new_files)
            # Note: commits happen per-file inside the indexer
            logger.info("Incremental file indexing task completed", source_id=source_id)
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Incremental file indexing failed", source_id=source_id, error=str(e), exc_info=True)
            await record_source_failure(db, source_id, e, f"Failed: {str(e)}")


async def run_retry_task(source_id: str, urls: list[str]):
    """Background task to retry failed URLs."""
    from .indexers.url import UrlIndexer

    async with async_session_maker() as db:
        try:
            indexer = UrlIndexer(db)
            await indexer.execute_retry(source_id, urls)
            await db.commit()
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Retry task failed", source_id=source_id, error=str(e))
            await record_source_failure(db, source_id, e, f"Retry failed: {str(e)}")


async def run_selective_index_task(source_id: str, urls: list[str]):
    """Background task to selectively re-index specific URLs."""
    from .indexers.url import UrlIndexer

    logger.info("Selective indexing task started", source_id=source_id, url_count=len(urls))
    async with async_session_maker() as db:
        try:
            indexer = UrlIndexer(db)
            await indexer.execute_selective_index(source_id, urls)
            await db.commit()
            logger.info("Selective indexing task completed", source_id=source_id)
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Selective indexing failed", source_id=source_id, error=str(e), exc_info=True)
            await record_source_failure(db, source_id, e, f"Selective refresh failed: {str(e)}")
