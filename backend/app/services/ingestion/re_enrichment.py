"""
Re-enrichment service.

Scrolls all existing Qdrant chunks for a knowledge source and re-runs
LLM classification on each one, updating the Qdrant payload metadata
with the classification result.

This is the background-job counterpart to the standalone
scripts/run_enrichment.py script.
"""
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source
from app.services.ingestion.enrichment import EnrichmentConfig, EnrichmentService
from app.services.ingestion.qdrant_client import get_qdrant_client

logger = structlog.get_logger()

DEFAULT_ENRICHMENT_MODEL = "qwen3:14b"
SCROLL_BATCH = 20


async def execute_re_enrichment(source_id: str, db: AsyncSession) -> None:
    """
    Scroll all Qdrant chunks for *source_id* and re-classify each one.

    Progress is tracked on the Source record so the UI can
    poll the standard /status endpoint to monitor progress.

    Args:
        source_id: UUID of the Source to re-enrich.
        db: Async database session (must be committed by the caller).
    """
    from sqlalchemy import select

    # --- Load source ---
    stmt = select(Source).where(Source.id == source_id)
    result = await db.execute(stmt)
    source: Optional[Source] = result.scalar_one_or_none()

    if not source:
        raise ValueError(f"Source not found: {source_id}")

    if not source.collection_name:
        raise ValueError(
            f"Source '{source.name}' has no Qdrant collection — index it first."
        )

    if not source.enrichment_taxonomy_id:
        raise ValueError(
            f"Source '{source.name}' has no enrichment taxonomy configured."
        )

    # --- Build enrichment config from source settings ---
    enrichment_model = source.enrichment_model or DEFAULT_ENRICHMENT_MODEL
    config = EnrichmentConfig(
        enabled=True,
        taxonomy_id=source.enrichment_taxonomy_id,
        classification_provider="ollama",
        classification_model=enrichment_model,
        classification_temperature=0.1,
        max_classification_chars=3000,
        document_type_detection=False,  # Skip text cleaning; classify raw stored content
    )

    # --- Initialise Qdrant and EnrichmentService ---
    qdrant = get_qdrant_client()
    enrichment_svc = EnrichmentService()
    collection = source.collection_name

    # Count total points for progress tracking
    try:
        collection_info = qdrant.get_collection(collection)
        total_points = collection_info.points_count or 0
    except Exception as exc:
        raise ValueError(f"Cannot access Qdrant collection '{collection}': {exc}") from exc

    if total_points == 0:
        source.status = "indexed"
        _update_progress(source, 0, 0, "No chunks found in collection — nothing to enrich")
        await db.commit()
        return

    # Update progress total now that we know how many points exist.
    # status is already "indexing" — set by the API endpoint before enqueueing.
    source.progress = 0
    source.progress_total = total_points
    source.progress_message = "Re-enrichment starting…"
    source.progress_updated_at = datetime.utcnow()
    await db.commit()

    # --- Scroll and classify ---
    classified = 0
    skipped = 0
    failed = 0
    offset = None

    while True:
        points, next_offset = qdrant.scroll(
            collection_name=collection,
            offset=offset,
            limit=SCROLL_BATCH,
            with_payload=True,
            with_vectors=False,
        )

        if not points:
            break

        for point in points:
            payload = point.payload or {}
            content: str = payload.get("content", "")
            source_field: str = payload.get("source", "")
            title_field: str = payload.get("title", "")
            metadata: dict = payload.get("metadata", {}) or {}

            if not content.strip():
                skipped += 1
                continue

            filename = source_field or title_field or "unknown"

            try:
                classification = await _classify_chunk(
                    text=content,
                    filename=filename,
                    config=config,
                    enrichment_svc=enrichment_svc,
                    db=db,
                )
            except Exception as exc:
                logger.warning(
                    "Chunk classification failed",
                    source_id=source_id,
                    point_id=point.id,
                    error=str(exc),
                )
                failed += 1
                continue

            if classification:
                updated_metadata = {**metadata, **classification}
                try:
                    qdrant.set_payload(
                        collection_name=collection,
                        payload={"metadata": updated_metadata},
                        points=[point.id],
                    )
                    classified += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to update Qdrant payload",
                        source_id=source_id,
                        point_id=point.id,
                        error=str(exc),
                    )
                    failed += 1
            else:
                failed += 1

        # Update progress after each batch
        processed = classified + skipped + failed
        _update_progress(
            source,
            processed,
            total_points,
            f"Re-enriching: {processed}/{total_points} chunks processed "
            f"(classified={classified}, skipped={skipped}, failed={failed})",
        )
        await db.commit()

        offset = next_offset
        if offset is None:
            break

    # --- Final status ---
    source.status = "indexed"
    source.progress = total_points
    source.progress_total = total_points
    source.progress_message = (
        f"Re-enrichment complete: {classified} classified, "
        f"{skipped} skipped, {failed} failed"
    )
    source.progress_updated_at = datetime.utcnow()
    source.last_indexed = datetime.utcnow()
    await db.commit()

    logger.info(
        "Re-enrichment complete",
        source_id=source_id,
        classified=classified,
        skipped=skipped,
        failed=failed,
        total=total_points,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _classify_chunk(
    text: str,
    filename: str,
    config: EnrichmentConfig,
    enrichment_svc: EnrichmentService,
    db: AsyncSession,
) -> Optional[dict]:
    """
    Run classification on a single chunk.

    Returns the classification dict (may be empty) or None if classification
    could not be performed. Delegates entirely to EnrichmentService so that
    taxonomy lookup, LLM call, and keyword fallback are handled consistently.
    """
    result = await enrichment_svc.enrich(
        text=text,
        filename=filename,
        config=config,
        db=db,
    )
    return result.get("classification")


def _update_progress(
    source: Source,
    current: int,
    total: int,
    message: str,
) -> None:
    """Update in-memory progress fields on the source object (caller commits)."""
    source.progress = current
    source.progress_total = total
    source.progress_message = message
    source.progress_updated_at = datetime.utcnow()
