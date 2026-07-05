"""
Backfill `documents` rows for libraries whose chunks exist in Qdrant
but never produced relational Document records.

Background
----------
Only the directory indexer wrote `Document` rows. URL/file/Tika indexers
stored chunks in Qdrant but skipped the relational write, so most libraries
show non-zero `library.document_count` while their `documents` table is empty.

This script reads Qdrant chunk payloads, groups them per (library, document),
and calls `DocumentService.upsert_document(...)` to materialize one row per
group. After backfill it runs `LibraryService.recalculate_stats(...)` so the
card and tab counts match.

Usage (run inside the backend container; cwd = /app/backend):
    python -m scripts.backfill_documents --dry-run
    python -m scripts.backfill_documents
    python -m scripts.backfill_documents --library-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

# Ensure `app` package is importable when run as `python -m scripts.backfill_documents`
# from the backend container (cwd is /app/backend, which contains both `app/` and `scripts/`).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from sqlalchemy import select, func  # noqa: E402

from app.core.database import async_session_maker  # noqa: E402
from app.models import Library, Document, LibrarySource, Source  # noqa: E402
from app.services.library import DocumentService, LibraryService  # noqa: E402
from app.services.ingestion.qdrant_client import get_qdrant_client  # noqa: E402


# Group key prefix tags so we can report fallback usage clearly.
KEY_PREFERRED = "preferred"   # payload had document_id + library_id
KEY_FALLBACK_HASH = "hash"    # synthesized from (source_id, source)
KEY_FALLBACK_SRC = "source"   # last-resort: grouped by source field only


@dataclass
class DocGroup:
    """In-memory aggregate of all chunks that belong to one document."""

    document_id: str
    library_id: str
    source_id: Optional[str] = None
    title: Optional[str] = None
    source_value: Optional[str] = None  # the raw "source" payload (path or URL)
    file_type: Optional[str] = None
    document_type: Optional[str] = None
    classification: Optional[dict] = None
    chunk_count: int = 0
    keyspace: str = KEY_PREFERRED
    sample_payload: Optional[dict] = field(default=None, repr=False)


def _looks_like_url(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"}
    except Exception:
        return False


def _file_type_from_source(source: Optional[str]) -> Optional[str]:
    if not source:
        return None
    if _looks_like_url(source):
        return "html"
    name = source.rstrip("/").split("/")[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[1].lower()
        return ext or None
    return None


def _title_from_source(source: Optional[str]) -> str:
    if not source:
        return ""
    if _looks_like_url(source):
        parsed = urlparse(source)
        path = parsed.path.rstrip("/")
        if path:
            return path.split("/")[-1] or parsed.netloc
        return parsed.netloc or source
    return source.rstrip("/").split("/")[-1] or source


def _synthesize_document_id(source_id: Optional[str], locator: str) -> str:
    """Stable fallback id when payload didn't carry document_id."""
    seed = f"{source_id or 'unknown'}:{locator or ''}"
    return hashlib.md5(seed.encode("utf-8")).hexdigest()


def _classify_payload(payload: dict, library_kb_id: str) -> tuple[str, str, str]:
    """Return (keyspace, library_id, document_id) for the given chunk payload."""
    payload_lib = payload.get("library_id")
    payload_doc = payload.get("document_id")
    if payload_lib and payload_doc:
        return KEY_PREFERRED, str(payload_lib), str(payload_doc)

    source_id = payload.get("source_id")
    source_value = payload.get("source") or ""
    if source_id or source_value:
        synth = _synthesize_document_id(source_id, source_value)
        return KEY_FALLBACK_HASH, library_kb_id, synth

    # Last resort — group everything missing identifiers under a single bucket
    # keyed by a fixed sentinel so the script doesn't crash; user will need a
    # full re-index to recover anything meaningful.
    return KEY_FALLBACK_SRC, library_kb_id, _synthesize_document_id(None, "__no_identifier__")


def _payload_title(payload: dict) -> Optional[str]:
    title = payload.get("title")
    if title:
        return title
    metadata = payload.get("metadata") or {}
    return metadata.get("title")


def _payload_file_type(payload: dict) -> Optional[str]:
    metadata = payload.get("metadata") or {}
    return metadata.get("file_type") or _file_type_from_source(payload.get("source"))


def _payload_document_type(payload: dict) -> Optional[str]:
    metadata = payload.get("metadata") or {}
    return metadata.get("document_type")


async def _scroll_collection(client, collection_name: str, batch: int = 1000):
    """Yield payloads from the entire collection."""
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            offset=offset,
            limit=batch,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return
        for point in points:
            payload = point.payload or {}
            yield payload
        if next_offset is None:
            return
        offset = next_offset


async def _list_library_collections(session, library: Library) -> list[tuple[str, Optional[str]]]:
    """Return [(collection_name, source_id), ...] for all collections that hold
    this library's chunks.

    In this Agentbase instance, chunks live in **source-level** collections
    (the library's own ``collection_name`` is rarely populated for older
    libraries). So we enumerate the library's bound sources and scan each
    one's collection. We also include the library's own collection in case a
    newer fan-out path wrote there.
    """
    seen: set[str] = set()
    collections: list[tuple[str, Optional[str]]] = []

    if library.collection_name:
        collections.append((library.collection_name, None))
        seen.add(library.collection_name)

    result = await session.execute(
        select(Source)
        .join(LibrarySource, LibrarySource.source_id == Source.id)
        .where(LibrarySource.library_id == library.id)
    )
    for source in result.scalars().all():
        coll = source.collection_name
        if coll and coll not in seen:
            collections.append((coll, source.id))
            seen.add(coll)
    return collections


async def _build_groups(
    client,
    library: Library,
    collections: list[tuple[str, Optional[str]]],
) -> tuple[dict[tuple[str, str], DocGroup], dict[str, int], list[str]]:
    """Scan all of a library's source collections and aggregate groups.

    Returns (groups, keyspace_counts, missing_collections).
    """
    groups: dict[tuple[str, str], DocGroup] = {}
    keyspace_counts = {KEY_PREFERRED: 0, KEY_FALLBACK_HASH: 0, KEY_FALLBACK_SRC: 0}
    missing: list[str] = []

    for collection_name, source_hint in collections:
        try:
            async for payload in _scroll_collection(client, collection_name):
                # Some chunks in a shared source collection may belong to a
                # different library. If the payload carries an explicit
                # library_id, only consume chunks tagged for THIS library.
                payload_lib = payload.get("library_id")
                if payload_lib and str(payload_lib) != library.id:
                    continue

                keyspace, lib_id, doc_id = _classify_payload(payload, library.id)
                keyspace_counts[keyspace] += 1
                # Always attribute to the library we're backfilling for —
                # the upsert target is per-library.
                lib_id = library.id

                # If the payload didn't carry source_id, fall back to the
                # source the collection belongs to (when known).
                payload_source_id = payload.get("source_id") or source_hint

                key = (lib_id, doc_id)
                group = groups.get(key)
                if group is None:
                    group = DocGroup(
                        document_id=doc_id,
                        library_id=lib_id,
                        source_id=payload_source_id,
                        title=_payload_title(payload),
                        source_value=payload.get("source"),
                        file_type=_payload_file_type(payload),
                        document_type=_payload_document_type(payload),
                        classification=None,
                        chunk_count=0,
                        keyspace=keyspace,
                        sample_payload=payload,
                    )
                    groups[key] = group
                else:
                    if not group.source_id and payload_source_id:
                        group.source_id = payload_source_id
                    if not group.title:
                        title = _payload_title(payload)
                        if title:
                            group.title = title
                    if not group.source_value and payload.get("source"):
                        group.source_value = payload.get("source")
                    if not group.file_type:
                        ft = _payload_file_type(payload)
                        if ft:
                            group.file_type = ft
                    if not group.document_type:
                        dt = _payload_document_type(payload)
                        if dt:
                            group.document_type = dt

                group.chunk_count += 1
        except Exception as exc:
            # Treat 404 / missing collection as soft failure — many older
            # libraries reference a library-level collection that was never
            # created. Other source collections may still yield data.
            missing.append(f"{collection_name}: {exc}")
            continue

    return groups, keyspace_counts, missing


async def _existing_document_count(session, library_id: str) -> int:
    result = await session.execute(
        select(func.count(Document.id)).where(Document.library_id == library_id)
    )
    return int(result.scalar() or 0)


async def _backfill_library(
    session,
    library: Library,
    *,
    dry_run: bool,
) -> dict:
    """Backfill one library. Returns a stats dict."""
    client = get_qdrant_client()
    started = time.monotonic()

    existing = await _existing_document_count(session, library.id)
    expected = int(library.document_count or 0)
    threshold = math.ceil(0.9 * expected) if expected else 0
    skipped_populated = expected > 0 and existing >= threshold

    stats = {
        "library_id": library.id,
        "library_name": library.name,
        "collection": library.collection_name,
        "expected": expected,
        "existing": existing,
        "skipped_populated": skipped_populated,
        "chunks": 0,
        "groups": 0,
        "created": 0,
        "updated": 0,
        "errors": 0,
        "keyspace": {KEY_PREFERRED: 0, KEY_FALLBACK_HASH: 0, KEY_FALLBACK_SRC: 0},
        "elapsed": 0.0,
        "after_count": existing,
        "scanned_collections": 0,
        "total_collections": 0,
    }

    if skipped_populated:
        print(
            f"[Library: {library.name}] collection={library.collection_name} "
            f"expected={expected} existing={existing} -> skipped (populated)"
        )
        return stats

    # Resolve which Qdrant collections hold this library's chunks.
    collections = await _list_library_collections(session, library)
    if not collections:
        print(
            f"[Library: {library.name}] no collections to scan; skipping"
        )
        return stats

    # Build groups from Qdrant
    try:
        groups, keyspace_counts, missing = await _build_groups(client, library, collections)
    except Exception as exc:
        print(
            f"[Library: {library.name}] ERROR scanning collections: {exc}"
        )
        stats["errors"] += 1
        return stats

    if missing:
        for m in missing:
            print(f"  [Library: {library.name}] (skipped collection) {m}")

    stats["chunks"] = sum(keyspace_counts.values())
    stats["groups"] = len(groups)
    stats["keyspace"] = keyspace_counts
    stats["scanned_collections"] = len(collections) - len(missing)
    stats["total_collections"] = len(collections)

    coll_label = (
        f"collections={stats['scanned_collections']}/{stats['total_collections']}"
    )
    if not groups:
        elapsed = time.monotonic() - started
        stats["elapsed"] = elapsed
        print(
            f"[Library: {library.name}] {coll_label} "
            f"chunks=0 groups=0 (no chunks found, skipping)"
        )
        return stats

    if dry_run:
        elapsed = time.monotonic() - started
        stats["elapsed"] = elapsed
        keyspace_summary = (
            f"preferred={keyspace_counts[KEY_PREFERRED]} "
            f"fallback_hash={keyspace_counts[KEY_FALLBACK_HASH]} "
            f"fallback_src={keyspace_counts[KEY_FALLBACK_SRC]}"
        )
        print(
            f"[Library: {library.name}] {coll_label} "
            f"chunks={stats['chunks']} groups={stats['groups']} "
            f"(dry-run; would upsert {stats['groups']} documents) "
            f"[{keyspace_summary}] (took {elapsed:.1f}s)"
        )
        return stats

    # Live run — upsert each group via DocumentService
    doc_service = DocumentService(session)

    created = 0
    updated = 0
    errors = 0
    for (lib_id, doc_id), group in groups.items():
        # Was this document already present? Determines created vs updated count.
        existing_doc = await doc_service.get_document_by_document_id(lib_id, doc_id)

        title = group.title or _title_from_source(group.source_value) or doc_id
        is_url = _looks_like_url(group.source_value)
        url_value = group.source_value if is_url else None
        file_path_value = None if is_url else group.source_value
        file_type_value = group.file_type or _file_type_from_source(group.source_value)
        document_type_value = group.document_type or "standard"

        try:
            await doc_service.upsert_document(
                library_id=lib_id,
                source_id=group.source_id,  # may be None — Document.source_id is nullable
                document_id=doc_id,
                title=title,
                full_text="",          # chunks aren't worth re-stitching
                content_hash="",
                file_path=file_path_value,
                file_type=file_type_value,
                url=url_value,
                classification=group.classification,
                document_type=document_type_value,
                chunk_count=group.chunk_count,
            )
            if existing_doc:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            errors += 1
            print(
                f"  ! upsert failed for library={lib_id} document_id={doc_id}: {exc}"
            )

    # Commit per library
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        print(f"[Library: {library.name}] commit FAILED: {exc}")
        stats["errors"] = errors + 1
        return stats

    # Recalculate stats so the card matches the tab
    try:
        kb_service = LibraryService(session)
        await kb_service.recalculate_stats(library.id)
    except Exception as exc:
        print(f"[Library: {library.name}] recalculate_stats failed: {exc}")

    after_count = await _existing_document_count(session, library.id)

    elapsed = time.monotonic() - started
    stats["created"] = created
    stats["updated"] = updated
    stats["errors"] = errors
    stats["elapsed"] = elapsed
    stats["after_count"] = after_count

    keyspace_summary = (
        f"preferred={keyspace_counts[KEY_PREFERRED]} "
        f"fallback_hash={keyspace_counts[KEY_FALLBACK_HASH]} "
        f"fallback_src={keyspace_counts[KEY_FALLBACK_SRC]}"
    )
    print(
        f"[Library: {library.name}] {coll_label} "
        f"chunks={stats['chunks']} -> groups={stats['groups']} "
        f"created={created} updated={updated} errors={errors} "
        f"[{keyspace_summary}] (took {elapsed:.1f}s)"
    )
    return stats


async def _select_libraries(session, library_id: Optional[str]) -> list[Library]:
    stmt = select(Library)
    if library_id:
        stmt = stmt.where(Library.id == library_id)
    stmt = stmt.order_by(Library.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def run(dry_run: bool, library_id: Optional[str]) -> int:
    started = time.monotonic()
    print(
        f"=== Document backfill starting at {datetime.utcnow().isoformat()}Z "
        f"(dry_run={dry_run}, library_id={library_id or 'ALL'}) ==="
    )

    summaries: list[dict] = []
    async with async_session_maker() as session:
        libraries = await _select_libraries(session, library_id)
        if not libraries:
            print("No libraries matched the filter; nothing to do.")
            return 0

        for library in libraries:
            # Skip libraries that have no expected docs and no existing rows
            existing = await _existing_document_count(session, library.id)
            if (library.document_count or 0) == 0 and existing == 0:
                print(
                    f"[Library: {library.name}] expected=0 existing=0 -> skipping (empty)"
                )
                continue
            summary = await _backfill_library(session, library, dry_run=dry_run)
            summaries.append(summary)

    elapsed = time.monotonic() - started
    print()
    print("=== Summary ===")
    print(
        f"{'Library':<40} {'expected':>9} {'before':>7} {'groups':>7} "
        f"{'created':>8} {'updated':>8} {'after':>7} {'elapsed':>8}"
    )
    for s in summaries:
        print(
            f"{s['library_name'][:40]:<40} {s['expected']:>9} {s['existing']:>7} "
            f"{s['groups']:>7} {s['created']:>8} {s['updated']:>8} "
            f"{s['after_count']:>7} {s['elapsed']:>7.1f}s"
        )
    print(f"Total elapsed: {elapsed:.1f}s")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing to the DB.",
    )
    parser.add_argument(
        "--library-id",
        type=str,
        default=None,
        help="Backfill only the library with this UUID.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(run(dry_run=args.dry_run, library_id=args.library_id))


if __name__ == "__main__":
    raise SystemExit(main())
