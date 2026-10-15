"""
Re-enrichment service.

Scrolls all existing Qdrant chunks for a knowledge source and re-runs
LLM classification on each one, updating the Qdrant payload metadata
with the classification result — and backfilling DocumentContent rows
so taxonomy coverage / stale detection move without a full re-index (#26).
"""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentContent, Source
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

    # Preload DocumentContent rows for backfill matching (#26).
    dc_rows = list(
        (
            await db.execute(
                select(DocumentContent).where(DocumentContent.source_id == source_id)
            )
        ).scalars().all()
    )
    dc_index = _build_document_content_index(dc_rows)

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

    # Aggregate per-document classifications for DocumentContent backfill.
    # Keyed by DocumentContent.id when matched; values are lists of
    # classification dicts + method/taxonomy attribution from chunks.
    doc_classifications: dict[str, list[dict]] = defaultdict(list)
    doc_methods: dict[str, list[str]] = defaultdict(list)
    doc_taxonomy: dict[str, tuple[str, int]] = {}

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
                enrich_out = await _classify_chunk(
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

            classification = enrich_out.get("classification") if enrich_out else None
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
                    continue

                dc = _match_document_content(dc_index, source_field, payload)
                if dc is not None:
                    doc_classifications[dc.id].append(classification)
                    method = enrich_out.get("classification_method")
                    if method:
                        doc_methods[dc.id].append(method)
                    tax_id = enrich_out.get("taxonomy_id")
                    tax_ver = enrich_out.get("taxonomy_version")
                    if tax_id is not None and tax_ver is not None:
                        doc_taxonomy[dc.id] = (tax_id, tax_ver)
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

    # --- Backfill DocumentContent from aggregated chunk classifications (#26) ---
    dc_by_id = {row.id: row for row in dc_rows}
    backfilled = 0
    for dc_id, class_list in doc_classifications.items():
        dc = dc_by_id.get(dc_id)
        if not dc:
            continue
        merged = _merge_classifications(class_list)
        if not merged:
            continue
        dc.classification = merged
        methods = doc_methods.get(dc_id) or []
        if methods:
            # Prefer llm if any chunk used it; else most common.
            dc.classification_method = (
                "llm" if "llm" in methods else Counter(methods).most_common(1)[0][0]
            )
        tax_info = doc_taxonomy.get(dc_id)
        if tax_info:
            dc.taxonomy_id, dc.classification_taxonomy_version = tax_info
        backfilled += 1

    if backfilled:
        await db.flush()

    # --- Final status ---
    source.status = "indexed"
    source.progress = total_points
    source.progress_total = total_points
    source.progress_message = (
        f"Re-enrichment complete: {classified} classified, "
        f"{skipped} skipped, {failed} failed"
        + (f", {backfilled} documents backfilled" if backfilled else "")
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
        documents_backfilled=backfilled,
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

    Returns a dict with classification / method / taxonomy attribution, or
    None if classification could not be performed.
    """
    result = await enrichment_svc.enrich(
        text=text,
        filename=filename,
        config=config,
        db=db,
    )
    if not result.get("classification"):
        return None
    return {
        "classification": result.get("classification"),
        "classification_method": result.get("classification_method"),
        "taxonomy_id": result.get("taxonomy_id"),
        "taxonomy_version": result.get("taxonomy_version"),
    }


def _build_document_content_index(
    rows: list[DocumentContent],
) -> dict[str, DocumentContent]:
    """Build lookup keys → DocumentContent for chunk→row matching.

    Keys include exact url, exact file_path, and basename forms so relative
    Qdrant ``source`` paths (directory indexers) can resolve to absolute
    DocumentContent.url keys (#26).
    """
    index: dict[str, DocumentContent] = {}
    for row in rows:
        if row.url:
            index[row.url] = row
            index[_basename(row.url)] = row
        if row.file_path:
            index[row.file_path] = row
            index[_basename(row.file_path)] = row
    return index


def _match_document_content(
    index: dict[str, DocumentContent],
    source_field: str,
    payload: dict,
) -> Optional[DocumentContent]:
    """Resolve a chunk payload to its DocumentContent row."""
    if not index:
        return None

    candidates = []
    if source_field:
        candidates.append(source_field)
        candidates.append(_basename(source_field))
    # Some indexers store the absolute path under file_path in metadata.
    meta = payload.get("metadata") or {}
    for key in ("file_path", "path", "url"):
        val = meta.get(key) or payload.get(key)
        if val:
            candidates.append(val)
            candidates.append(_basename(str(val)))

    for key in candidates:
        hit = index.get(key)
        if hit is not None:
            return hit

    # Suffix match: DocumentContent.url is absolute, chunk source is relative.
    if source_field:
        for url_key, row in index.items():
            if url_key.endswith(source_field) or source_field.endswith(url_key):
                return row
    return None


def _basename(path: str) -> str:
    """Return the final path component, handling both POSIX and Windows paths."""
    if not path:
        return path
    name = PurePosixPath(path).name
    if "\\" in path:
        name = PureWindowsPath(path).name or name
    return name


def _merge_classifications(class_list: list[dict]) -> dict:
    """Majority-vote merge of per-chunk classification dicts into one doc-level dict."""
    if not class_list:
        return {}
    if len(class_list) == 1:
        return dict(class_list[0])

    keys = set()
    for c in class_list:
        keys.update(c.keys())

    merged: dict = {}
    for key in keys:
        values = [c[key] for c in class_list if key in c and c[key] not in (None, "", [])]
        if not values:
            continue
        # Hashable values → majority vote; else take first.
        try:
            merged[key] = Counter(
                tuple(v) if isinstance(v, list) else v for v in values
            ).most_common(1)[0][0]
            # Restore lists that were tuple-ized for hashing.
            if isinstance(merged[key], tuple):
                merged[key] = list(merged[key])
        except TypeError:
            merged[key] = values[0]
    return merged


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
