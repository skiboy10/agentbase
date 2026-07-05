"""
One-time backfill: populate empty ``Document.full_text`` so library documents
are viewable in the UI (#100).

Background
----------
The 2026-05-05 document backfill (``backfill_documents.py``) created Document
rows from existing Qdrant chunks with ``full_text=""`` ("chunks aren't worth
re-stitching"). Those documents open as a blank viewer in the library
Documents tab. New ingestion populates ``full_text`` correctly; this repairs
the legacy rows.

Repair strategy, best fidelity first:

1. **DocumentContent match** — URL sources store the original scraped text in
   ``document_content.raw_content``. Match on URL / document_id and copy it.
2. **Qdrant stitch** — otherwise, reassemble the text from the source
   collection's chunk payloads (ordered by ``chunk_index``), trimming the
   splitter overlap where consecutive chunks share a suffix/prefix.

Only rows with empty ``full_text`` are touched; re-running is a no-op once
repaired.

Usage (inside the backend container)::

    python -m scripts.backfill_document_text            # dry-run (report only)
    python -m scripts.backfill_document_text --apply    # write repaired text
    python -m scripts.backfill_document_text --apply --library <LIBRARY_ID>
"""
import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import or_, select

from app.core.database import async_session_maker
from app.models import Document, DocumentContent, Source
from app.services.ingestion.qdrant_client import get_qdrant_client
from qdrant_client.models import FieldCondition, Filter, MatchValue

SCROLL_PAGE = 500
# Bound the suffix/prefix overlap search; must exceed the splitter's
# chunk_overlap (default 200) with headroom.
MAX_OVERLAP_SCAN = 800
# Shorter matches are boundary coincidence (a shared word or character),
# not splitter overlap — slicing them off would corrupt the text.
MIN_OVERLAP = 20


def stitch_chunks(chunks: list[tuple[int, str]]) -> str:
    """Reassemble document text from (chunk_index, content) pairs.

    Consecutive splitter chunks repeat ``chunk_overlap`` characters; when the
    end of the accumulated text matches the start of the next chunk, the
    duplicate region is emitted once. Non-contiguous chunks fall back to a
    paragraph join.
    """
    ordered = [c for _, c in sorted(chunks, key=lambda x: x[0] or 0)]
    if not ordered:
        return ""
    text = ordered[0]
    for nxt in ordered[1:]:
        window = min(MAX_OVERLAP_SCAN, len(text), len(nxt))
        overlap = 0
        for k in range(window, MIN_OVERLAP - 1, -1):
            if text[-k:] == nxt[:k]:
                overlap = k
                break
        text = text + nxt[overlap:] if overlap else text + "\n\n" + nxt
    return text


def _chunks_by_document(client, collection: str, source_id: str) -> dict[str, list[tuple[int, str]]]:
    """Group a source collection's chunk payloads by document identifier.

    Keyed by payload ``document_id`` when present, else by the ``source``
    locator (URL or file path) — the same keys the document backfill used.
    """
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    offset = None
    flt = Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))])
    try:
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                scroll_filter=flt,
                limit=SCROLL_PAGE,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for p in points:
                payload = p.payload or {}
                content = payload.get("content")
                if not content:
                    continue
                key = payload.get("document_id") or payload.get("source")
                if not key:
                    continue
                try:
                    idx = int(payload.get("chunk_index") or 0)
                except (TypeError, ValueError):
                    idx = 0
                groups[key].append((idx, content))
            if offset is None:
                break
    except Exception as exc:
        print(f"  WARN  scroll failed for {collection}: {exc} — proceeding with partial data")
    return groups


async def main(apply: bool, library_id: str | None) -> None:
    client = get_qdrant_client()
    try:
        await _run(client, apply, library_id)
    finally:
        client.close()


async def _run(client, apply: bool, library_id: str | None) -> None:
    async with async_session_maker() as db:
        stmt = (
            select(Document, Source)
            .join(Source, Source.id == Document.source_id)
            .where(or_(Document.full_text.is_(None), Document.full_text == ""))
            .order_by(Source.id)
        )
        if library_id:
            stmt = stmt.where(Document.library_id == library_id)
        rows = (await db.execute(stmt)).all()

        print(f"{'MODE':<8}{'APPLY' if apply else 'DRY-RUN'}   ({len(rows)} empty documents)")
        repaired_dc = repaired_stitch = deleted_dupes = unmatched = 0
        stitch_cache: dict[str, dict[str, list[tuple[int, str]]]] = {}
        content_cache: dict[str, dict[str, str]] = {}
        dupe_cache: dict[str, set[tuple[str, str]]] = {}

        async def _populated_keys(source_id: str) -> set[tuple[str, str]]:
            """Per-source (library_id, locator) keys of rows that DO have text.

            A re-index after the 2026-05-05 backfill created fresh, populated
            rows whose document_id didn't match the backfill's synthesized
            ids — leaving the empty originals behind as true duplicates.
            Filling those would double every document in the library UI;
            they must be deleted instead.
            """
            if source_id not in dupe_cache:
                pop_rows = (
                    await db.execute(
                        select(Document.library_id, Document.url, Document.title).where(
                            Document.source_id == source_id,
                            Document.full_text.is_not(None),
                            Document.full_text != "",
                        )
                    )
                ).all()
                keys: set[tuple[str, str]] = set()
                for lib, url, title in pop_rows:
                    if url:
                        keys.add((lib, url))
                    if title:
                        keys.add((lib, title))
                dupe_cache[source_id] = keys
            return dupe_cache[source_id]

        async def _content_by_locator(source_id: str) -> dict[str, str]:
            """Per-source map of document_content URL/locator -> raw text."""
            if source_id not in content_cache:
                dc_rows = (
                    await db.execute(
                        select(DocumentContent.url, DocumentContent.raw_content).where(
                            DocumentContent.source_id == source_id
                        )
                    )
                ).all()
                content_cache[source_id] = {u: t for u, t in dc_rows if u and t}
            return content_cache[source_id]

        for doc, source in rows:
            # Pass 0: if a populated row for the same document already exists
            # in this library, the empty row is a duplicate — delete it.
            populated = await _populated_keys(source.id)
            if any(
                (doc.library_id, v) in populated for v in (doc.url, doc.title) if v
            ):
                deleted_dupes += 1
                verb = "DEL" if apply else "PLAN-DEL"
                print(f"  {verb:<8} {(doc.title or doc.document_id)[:50]:50} (duplicate of populated row)")
                if apply:
                    await db.delete(doc)
                continue

            # Pass 1: original scraped text from document_content.
            by_locator = await _content_by_locator(source.id)
            raw = next(
                (by_locator[v] for v in (doc.url, doc.document_id, doc.file_path) if v and v in by_locator),
                None,
            )

            if raw:
                new_text, how = raw, "content"
            else:
                # Pass 2: stitch from the source collection's chunks.
                if not source.collection_name:
                    unmatched += 1
                    print(f"  MISS  {(doc.title or doc.document_id)[:52]:52} (source has no collection)")
                    continue
                if source.id not in stitch_cache:
                    stitch_cache[source.id] = _chunks_by_document(
                        client, source.collection_name, source.id
                    )
                groups = stitch_cache[source.id]
                chunks = next(
                    (groups[k] for k in [doc.document_id, doc.url, doc.file_path] if k and k in groups),
                    None,
                )
                if not chunks:
                    unmatched += 1
                    print(f"  MISS  {(doc.title or doc.document_id)[:52]:52} (no content source found)")
                    continue
                new_text, how = stitch_chunks(chunks), "stitch"

            if apply:
                doc.full_text = new_text
                doc.text_length = len(new_text)
            # A row we just populated makes any later empty row with the same
            # locators a duplicate — record its keys so Pass 0 catches them.
            for v in (doc.url, doc.title):
                if v:
                    dupe_cache.setdefault(source.id, set()).add((doc.library_id, v))
            if how == "content":
                repaired_dc += 1
            else:
                repaired_stitch += 1
            verb = "FIX" if apply else "PLAN"
            print(f"  {verb:<5} {(doc.title or doc.document_id)[:52]:52} {how} ({len(new_text)} chars)")

        if apply:
            await db.commit()
        print(
            f"\n{'REPAIRED' if apply else 'WOULD REPAIR'}: "
            f"{repaired_dc} from document_content, {repaired_stitch} stitched, "
            f"{deleted_dupes} duplicate rows deleted, {unmatched} unmatched"
        )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write repaired text (default: dry-run)")
    ap.add_argument("--library", default=None, help="Limit to a single library id")
    args = ap.parse_args()
    asyncio.run(main(apply=args.apply, library_id=args.library))
