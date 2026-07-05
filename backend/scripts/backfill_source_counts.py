"""
One-time backfill: repair stale ``Source.chunk_count`` / ``Source.document_count``
rollups (#175).

Background
----------
Some finalize paths (notably the file indexer before the #175 fix) wrote the
Source counters inconsistently, leaving ``status = "indexed"`` sources with
``chunk_count = 0`` even though their Qdrant collection holds real points.
Retrieval is unaffected (search reads Qdrant), but the Sources UI and derived
stats under-report.

This script recomputes, for every indexed source:

- ``chunk_count``  — the number of points in the source's own Qdrant collection
  whose payload ``source_id`` matches (the same population the read path
  queries, making it the authoritative count).
- ``document_count`` — the number of ``documents`` rows for the source when it
  is library-bound (authoritative per-doc store), else the number of completed
  ``indexing_logs`` entries.

Only mismatched rows are touched; the script is idempotent and safe to re-run.

Usage (inside the backend container)::

    python -m scripts.backfill_source_counts            # dry-run (report only)
    python -m scripts.backfill_source_counts --apply    # write corrected counts
    python -m scripts.backfill_source_counts --apply --source <SOURCE_ID>
"""
import argparse
import asyncio

from sqlalchemy import func, select

from app.core.database import async_session_maker
from app.models import Document, IndexingLog, Source
from app.services.ingestion.qdrant_client import get_qdrant_client
from qdrant_client.models import FieldCondition, Filter, MatchValue

def _source_filter(source_id: str) -> Filter:
    return Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))])


def _count_points(client, collection: str, source_id: str) -> int | None:
    """Count points in ``collection`` whose payload.source_id matches.

    Returns None when the collection does not exist (can't assert a count).
    """
    try:
        client.get_collection(collection)
    except Exception:
        return None
    result = client.count(
        collection_name=collection,
        count_filter=_source_filter(source_id),
        exact=True,
    )
    return result.count


async def main(apply: bool, only_source: str | None) -> None:
    client = get_qdrant_client()
    try:
        await _run(client, apply, only_source)
    finally:
        client.close()


async def _run(client, apply: bool, only_source: str | None) -> None:
    async with async_session_maker() as db:
        stmt = select(Source).where(Source.status == "indexed").order_by(Source.name)
        if only_source:
            stmt = stmt.where(Source.id == only_source)
        sources = (await db.execute(stmt)).scalars().all()

        print(f"{'MODE':<8}{'APPLY' if apply else 'DRY-RUN'}   ({len(sources)} indexed sources)")
        fixed = 0
        for src in sources:
            if not src.collection_name:
                print(f"  SKIP  {src.name[:40]:40} (no collection name)")
                continue

            actual_chunks = _count_points(client, src.collection_name, src.id)
            if actual_chunks is None:
                print(f"  SKIP  {src.name[:40]:40} (collection {src.collection_name} absent)")
                continue

            # Documents are stored per (library, document) — a source bound to
            # N libraries has N rows per document. Source.document_count is a
            # per-source figure, so count distinct document ids.
            doc_rows = (
                await db.execute(
                    select(func.count(func.distinct(Document.document_id))).where(
                        Document.source_id == src.id
                    )
                )
            ).scalar_one()
            if doc_rows:
                actual_docs = doc_rows
            else:
                actual_docs = (
                    await db.execute(
                        select(func.count())
                        .select_from(IndexingLog)
                        .where(IndexingLog.source_id == src.id, IndexingLog.status == "done")
                    )
                ).scalar_one()

            chunk_stale = (src.chunk_count or 0) != actual_chunks
            # Only correct document_count when we have a non-zero authoritative
            # figure — an empty documents/log table proves nothing for legacy rows.
            doc_stale = actual_docs > 0 and (src.document_count or 0) != actual_docs
            if not chunk_stale and not doc_stale:
                continue

            label = (
                f"chunks {src.chunk_count or 0}→{actual_chunks}"
                + (f", docs {src.document_count or 0}→{actual_docs}" if doc_stale else "")
            )
            if apply:
                if chunk_stale:
                    src.chunk_count = actual_chunks
                if doc_stale:
                    src.document_count = actual_docs
                fixed += 1
                print(f"  FIX   {src.name[:40]:40} {label}")
            else:
                print(f"  PLAN  {src.name[:40]:40} {label}")

        if apply:
            await db.commit()
        print(f"\n{'FIXED' if apply else 'WOULD FIX'}: {fixed if apply else 'see PLAN lines'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write corrected counts (default: dry-run)")
    ap.add_argument("--source", default=None, help="Limit to a single source id")
    args = ap.parse_args()
    asyncio.run(main(apply=args.apply, only_source=args.source))
