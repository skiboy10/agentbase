"""
Backfill the ``folder_ancestors`` payload field on existing Qdrant chunks.

The sub-source filter overlay (Phase 2 of the folder-watcher consolidation)
relies on every chunk carrying a ``folder_ancestors`` keyword-indexed list
of canonical parent paths. New writes from the directory and file-item
indexers include this field; legacy chunks predating that change do not.

This script scrolls every directory/file source's Qdrant collection and
``set_payload`` s the missing fields. It is idempotent — re-running it leaves
already-backfilled chunks untouched (we re-compute and re-write, but the
value is deterministic from ``payload["source"]`` + the source's root path).

Usage::

    cd backend && uv run python -m scripts.backfill_folder_ancestors --dry-run
    cd backend && uv run python -m scripts.backfill_folder_ancestors
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import select

# Allow `python -m scripts.backfill_folder_ancestors` to find `app.*`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_maker  # noqa: E402
from app.models import Source  # noqa: E402
from app.services.ingestion.path_utils import (  # noqa: E402
    canonicalise_path,
    compute_folder_ancestors,
)
from app.services.ingestion.qdrant_client import get_qdrant_client  # noqa: E402
from app.services.rag.filters import KEYWORD_INDEX_FIELDS  # noqa: E402


logger = structlog.get_logger()
BATCH_SIZE = 256


def ensure_keyword_indexes(client, collection_name: str) -> None:
    """Create any missing keyword payload indexes on the collection.

    Backfilling the ``folder_ancestors`` field is only useful if the index
    exists — otherwise filter queries fall back to a full scan. Existing
    collections predating this PR may have been created before the
    ``folder_ancestors`` index was registered, so ensure it (and the rest
    of the canonical keyword index set) is present.
    """
    for field_name, field_schema in KEYWORD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
        except Exception:
            # Already exists or schema mismatch — safe to ignore for backfill
            pass


async def backfill_collection(client, source: Source, dry_run: bool) -> dict:
    """Backfill folder_ancestors for one source's collection.

    Returns a stats dict::

        {"source_id": str, "scanned": int, "updated": int, "skipped": int}
    """
    collection = source.collection_name
    if not collection:
        return {
            "source_id": source.id,
            "collection": None,
            "scanned": 0,
            "updated": 0,
            "skipped": 0,
        }

    root = source.source_path
    scanned = updated = skipped = 0
    offset = None

    # Ensure keyword indexes (including folder_ancestors) exist before
    # backfilling. Cheap if already present, free perf win if not.
    if not dry_run:
        ensure_keyword_indexes(client, collection)

    while True:
        try:
            points, next_offset = client.scroll(
                collection_name=collection,
                scroll_filter=None,
                limit=BATCH_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            msg = str(e)
            if "doesn't exist" in msg or "Not found" in msg or "404" in msg:
                logger.warning(
                    "Skipping source — Qdrant collection missing",
                    source_id=source.id,
                    collection=collection,
                )
                return {
                    "source_id": source.id,
                    "collection": collection,
                    "scanned": scanned,
                    "updated": updated,
                    "skipped": skipped,
                    "missing_collection": True,
                }
            raise
        if not points:
            break

        # Group by computed ancestors so we issue one set_payload per group.
        updates: dict[tuple[str, ...], list] = {}
        for p in points:
            scanned += 1
            payload = p.payload or {}
            raw_source = payload.get("source")
            if not raw_source:
                skipped += 1
                continue

            # If raw_source is relative (legacy directory chunks), resolve it
            # against the source root. If it's already absolute, canonicalise.
            if raw_source.startswith("/"):
                absolute = canonicalise_path(raw_source)
            else:
                absolute = canonicalise_path(str(Path(root) / raw_source))

            ancestors = tuple(compute_folder_ancestors(absolute, root=root))
            existing = payload.get("folder_ancestors")
            if existing and list(existing) == list(ancestors):
                # Already correct — no-op
                skipped += 1
                continue

            updates.setdefault(ancestors, []).append(p.id)

        for ancestors, ids in updates.items():
            if not ids:
                continue
            updated += len(ids)
            if dry_run:
                continue
            try:
                client.set_payload(
                    collection_name=collection,
                    payload={"folder_ancestors": list(ancestors)},
                    points=ids,
                    wait=False,
                )
            except Exception as e:
                logger.warning(
                    "set_payload failed",
                    collection=collection,
                    error=str(e),
                    batch_size=len(ids),
                )

        if not next_offset:
            break
        offset = next_offset

    logger.info(
        "Backfilled folder_ancestors for source",
        source_id=source.id,
        collection=collection,
        scanned=scanned,
        updated=updated,
        skipped=skipped,
        dry_run=dry_run,
    )
    return {
        "source_id": source.id,
        "collection": collection,
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute updates but don't write to Qdrant.",
    )
    parser.add_argument(
        "--source-id", default=None,
        help="Restrict to one source (UUID).",
    )
    args = parser.parse_args()

    client = get_qdrant_client()

    async with async_session_maker() as db:
        stmt = select(Source).where(
            Source.source_type.in_(["directory", "file"]),
            Source.collection_name.isnot(None),
            # Only roots own chunks; sub-sources (Phase 2) have no collection.
            Source.parent_source_id.is_(None),
        )
        if args.source_id:
            stmt = stmt.where(Source.id == args.source_id)
        sources = list((await db.execute(stmt)).scalars().all())

    if not sources:
        print("No directory/file sources with collections found.")
        return 0

    print(f"Backfilling folder_ancestors on {len(sources)} source(s){' (dry run)' if args.dry_run else ''}")
    totals = {"scanned": 0, "updated": 0, "skipped": 0}
    for source in sources:
        stats = await backfill_collection(client, source, dry_run=args.dry_run)
        for k in totals:
            totals[k] += stats[k]
        print(
            f"  {source.id} ({source.collection_name}): "
            f"scanned={stats['scanned']} updated={stats['updated']} skipped={stats['skipped']}"
        )

    print(f"\nTotal: scanned={totals['scanned']} updated={totals['updated']} skipped={totals['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
