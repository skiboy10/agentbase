"""
Job handlers for the worker loop.

Each handler receives a payload dict and manages its own database session.
These wrap the existing ingestion task functions.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
import structlog

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.models import WatcherEvent
from app.services.ingestion.background_tasks import (
    emit_source_indexed_event,
    record_source_failure,
)

logger = structlog.get_logger()


async def handle_index_source(payload: dict) -> None:
    """Handle index_source job — full indexing of a knowledge source."""
    from app.services.ingestion.orchestrator import IngestionService

    source_id = payload["source_id"]
    logger.info("Job handler: index_source started", source_id=source_id)

    async with async_session_maker() as db:
        try:
            service = IngestionService(db)
            await service.execute_indexing(source_id)
            await db.commit()
            logger.info("Job handler: index_source completed", source_id=source_id)
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Job handler: index_source failed", source_id=source_id, error=str(e))
            await record_source_failure(db, source_id, e, f"Failed: {str(e)}")
            raise  # Re-raise so the job worker marks it as failed


async def handle_incremental_index(payload: dict) -> None:
    """Handle incremental_index job — index only newly added files."""
    from app.services.ingestion.orchestrator import IngestionService

    source_id = payload["source_id"]
    new_files = payload["new_files"]
    logger.info("Job handler: incremental_index started", source_id=source_id, file_count=len(new_files))

    async with async_session_maker() as db:
        try:
            service = IngestionService(db)
            await service.execute_incremental_file_indexing(source_id, new_files)
            logger.info("Job handler: incremental_index completed", source_id=source_id)
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Job handler: incremental_index failed", source_id=source_id, error=str(e))
            await record_source_failure(db, source_id, e)
            raise


async def handle_retry_failed(payload: dict) -> None:
    """Handle retry_failed job — retry failed URLs."""
    from app.services.ingestion.indexers.url import UrlIndexer

    source_id = payload["source_id"]
    urls = payload["urls"]

    async with async_session_maker() as db:
        try:
            indexer = UrlIndexer(db)
            await indexer.execute_retry(source_id, urls)
            await db.commit()
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Job handler: retry_failed failed", source_id=source_id, error=str(e))
            await record_source_failure(db, source_id, e)
            raise


async def handle_selective_index(payload: dict) -> None:
    """Handle selective_index job — re-index specific URLs."""
    from app.services.ingestion.indexers.url import UrlIndexer

    source_id = payload["source_id"]
    urls = payload["urls"]
    logger.info("Job handler: selective_index started", source_id=source_id, url_count=len(urls))

    async with async_session_maker() as db:
        try:
            indexer = UrlIndexer(db)
            await indexer.execute_selective_index(source_id, urls)
            await db.commit()
            logger.info("Job handler: selective_index completed", source_id=source_id)
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Job handler: selective_index failed", source_id=source_id, error=str(e))
            await record_source_failure(db, source_id, e)
            raise


async def handle_watcher_events_gc(payload: dict) -> None:
    """Garbage-collect WatcherEvent rows.

    Two-pass retention, both server-side so we never load rows into memory
    (a chatty directory watcher can accumulate millions of events):
      1. Age cutoff — delete events older than ``watcher_events_retention_days``.
      2. Per-source cap — keep only the most recent ``watcher_events_max_per_source``
         events per source, so a single busy source can't dominate the table
         within the retention window.
    """
    from sqlalchemy import func, text as sql_text

    settings = get_settings()
    retention_days = settings.watcher_events_retention_days
    max_per_source = settings.watcher_events_max_per_source

    # WatcherEvent.timestamp is TIMESTAMP WITHOUT TIME ZONE; strip tzinfo on
    # the cutoff so asyncpg accepts the bind. Compute UTC instant first so
    # the cutoff value stays UTC-consistent.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).replace(tzinfo=None)
    logger.info("Job handler: watcher_events_gc started",
                cutoff=cutoff.isoformat(), max_per_source=max_per_source)

    # Pass 1: age-based deletion, committed on its own so its bulk row locks
    # are released before the heavier cap pass runs.
    async with async_session_maker() as db:
        age_result = await db.execute(
            delete(WatcherEvent).where(WatcherEvent.timestamp < cutoff)
        )
        await db.commit()
        deleted_by_age = age_result.rowcount

    # Pass 2: per-source cap. The HAVING pre-filter means the window function
    # only ranks sources that actually exceed the cap — an index-only scan on
    # ix_watcher_events_source_timestamp when none do. id DESC breaks ties on
    # equal timestamps so the retained set is deterministic.
    async with async_session_maker() as db:
        cap_result = await db.execute(
            sql_text(
                """
                DELETE FROM watcher_events
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id, row_number() OVER (
                            PARTITION BY source_id ORDER BY timestamp DESC, id DESC
                        ) AS rn
                        FROM watcher_events
                        WHERE source_id IN (
                            SELECT source_id FROM watcher_events
                            GROUP BY source_id HAVING COUNT(*) > :cap
                        )
                    ) ranked
                    WHERE ranked.rn > :cap
                )
                """
            ),
            {"cap": max_per_source},
        )
        await db.commit()
        deleted_by_cap = cap_result.rowcount

    logger.info("Job handler: watcher_events_gc completed",
                deleted_by_age=deleted_by_age, deleted_by_cap=deleted_by_cap)


async def handle_re_enrich_source(payload: dict) -> None:
    """Handle re_enrich_source job — LLM-classify all existing Qdrant chunks."""
    from app.services.ingestion.re_enrichment import execute_re_enrichment

    source_id = payload["source_id"]
    logger.info("Job handler: re_enrich_source started", source_id=source_id)

    async with async_session_maker() as db:
        try:
            await execute_re_enrichment(source_id, db)
            # execute_re_enrichment commits progress internally; final commit here
            # ensures the session is clean before the worker marks the job complete.
            await db.commit()
            logger.info("Job handler: re_enrich_source completed", source_id=source_id)
            # Re-enrichment isn't a fresh index run, but completion visibility
            # matters — emit source.indexed with the source's current counts/status.
            await emit_source_indexed_event(db, source_id)
        except Exception as e:
            logger.error("Job handler: re_enrich_source failed", source_id=source_id, error=str(e))
            await record_source_failure(db, source_id, e, f"Re-enrichment failed: {str(e)}")
            raise


async def handle_generate_questions(payload: dict) -> None:
    """Handle generate_questions job — draft eval questions from library docs."""
    from app.services.evaluation.generation import execute_question_generation
    from app.core.events import event_bus

    question_set_id = payload["question_set_id"]
    logger.info("Job handler: generate_questions started", question_set_id=question_set_id)

    async with async_session_maker() as db:
        created = await execute_question_generation(
            db,
            question_set_id=question_set_id,
            questions_per_doc=payload.get("questions_per_doc", 3),
            doc_sample_size=payload.get("doc_sample_size", 10),
            count=payload.get("count"),
        )
        await db.commit()
    await event_bus.publish(
        event_type="evaluation.questions_generated",
        payload={"question_set_id": question_set_id, "created": created},
        source="system",
    )


async def handle_run_scorecard(payload: dict) -> None:
    """Handle run_scorecard job — execute or re-judge an eval run."""
    from app.services.evaluation.runner import run_scorecard_task
    await run_scorecard_task(payload["run_id"], rejudge=payload.get("rejudge", False))
