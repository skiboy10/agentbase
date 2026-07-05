"""
One-time backfill: consolidate every library-bound source's chunks into the
source's OWN Qdrant collection (the primary copy the search/chat/coverage read
path queries).

Background
----------
Before the collection-routing fix, the indexer wrote a library-bound source's
chunks to the *library* collection only, while the read path resolves chunks via
``Source.collection_name`` (the source's own collection). Any chunk indexed after
a source was bound to a library therefore landed in a collection search never
queries — invisible.

The code fix makes the source's own collection the primary write target going
forward. This script repairs existing data by copying, for each library-bound
source, the points that live in a bound library's collection but are missing
from the source's own collection (matched by deterministic point id).

It is idempotent (upsert by id), safe to re-run, and copies only the *missing*
points (id-diff), so a collection that is already complete is a no-op.

Usage (inside the backend container)::

    python -m scripts.backfill_source_collections            # dry-run (report only)
    python -m scripts.backfill_source_collections --apply     # perform the copy
    python -m scripts.backfill_source_collections --apply --source <SOURCE_ID>
"""
import argparse
import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import Source, Library, LibrarySource
from app.services.ingestion.qdrant_client import get_qdrant_client
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointStruct

SCROLL_PAGE = 1000
COPY_BATCH = 128


def _source_filter(source_id: str) -> Filter:
    return Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))])


def _collection_exists(client, name: str) -> bool:
    try:
        client.get_collection(name)
        return True
    except Exception:
        return False


def _ids_for_source(client, collection: str, source_id: str) -> set:
    """All point ids in ``collection`` whose payload.source_id == source_id."""
    ids: set = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=_source_filter(source_id),
            limit=SCROLL_PAGE,
            with_payload=False,
            with_vectors=False,
            offset=offset,
        )
        ids.update(p.id for p in points)
        if offset is None:
            break
    return ids


def _copy_points(client, src_coll: str, lib_coll: str, ids: list) -> int:
    """Retrieve points (vectors + payload) from lib_coll and upsert into src_coll."""
    copied = 0
    for start in range(0, len(ids), COPY_BATCH):
        batch = ids[start:start + COPY_BATCH]
        records = client.retrieve(
            collection_name=lib_coll, ids=batch,
            with_payload=True, with_vectors=True,
        )
        points = [
            PointStruct(id=r.id, vector=r.vector, payload=r.payload)
            for r in records
        ]
        if points:
            client.upsert(collection_name=src_coll, points=points)
            copied += len(points)
    return copied


async def main(apply: bool, only_source: str | None) -> None:
    client = get_qdrant_client()
    async with async_session_maker() as db:
        stmt = (
            select(
                Source.id, Source.name, Source.collection_name,
                Library.collection_name, Library.embedding_dimensions,
            )
            .join(LibrarySource, LibrarySource.source_id == Source.id)
            .join(Library, Library.id == LibrarySource.library_id)
            .order_by(Source.name)
        )
        if only_source:
            stmt = stmt.where(Source.id == only_source)
        rows = (await db.execute(stmt)).all()

    print(f"{'MODE':<8}{'APPLY' if apply else 'DRY-RUN'}")
    total_copied = 0
    for sid, name, src_coll, lib_coll, dims in rows:
        if not src_coll or not lib_coll:
            print(f"  SKIP  {name[:40]:40} (missing collection name)")
            continue
        if not _collection_exists(client, lib_coll):
            print(f"  SKIP  {name[:40]:40} (library collection absent)")
            continue
        # Ensure the source collection exists before we copy into it.
        if not _collection_exists(client, src_coll):
            print(f"  WARN  {name[:40]:40} source collection {src_coll} absent — skipping "
                  f"(re-index the source to create it, then re-run)")
            continue

        src_ids = _ids_for_source(client, src_coll, sid)
        lib_ids = _ids_for_source(client, lib_coll, sid)
        missing = list(lib_ids - src_ids)
        if not missing:
            print(f"  OK    {name[:40]:40} complete (src={len(src_ids)}, lib={len(lib_ids)})")
            continue

        if apply:
            copied = _copy_points(client, src_coll, lib_coll, missing)
            total_copied += copied
            print(f"  COPY  {name[:40]:40} +{copied} (src {len(src_ids)}→{len(src_ids)+copied}, "
                  f"lib={len(lib_ids)})")
        else:
            print(f"  PLAN  {name[:40]:40} would copy {len(missing)} "
                  f"(src={len(src_ids)}, lib={len(lib_ids)})")

    print(f"\n{'COPIED' if apply else 'WOULD COPY'} total: {total_copied if apply else 'see PLAN lines'}")
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Perform the copy (default: dry-run)")
    ap.add_argument("--source", default=None, help="Limit to a single source id")
    args = ap.parse_args()
    asyncio.run(main(apply=args.apply, only_source=args.source))
