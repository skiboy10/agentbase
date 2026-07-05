"""Backfill publish-date facets onto already-indexed YouTube transcript chunks.

Data-only: reads each chunk's existing nested ``metadata.upload_date`` and writes
``published_date`` / ``published_year`` / ``published_month`` alongside it, then
ensures the new payload indexes exist. No re-fetch, no re-embed.

Idempotent — re-running merges the same facets and is a no-op for chunks that
already have them.

The only input consumed is the structured ``upload_date`` field (yt-dlp
metadata); transcript prose is never read or interpreted here.

Usage (inside the backend container):
    python -m scripts.backfill_youtube_date_facets            # all youtube sources
    python -m scripts.backfill_youtube_date_facets --dry-run  # report only
    python -m scripts.backfill_youtube_date_facets --source-id <id>
"""
import argparse
import asyncio
from collections import defaultdict

from qdrant_client import models
from sqlalchemy import select, and_

from app.core.database import async_session_maker
from app.models import Source, Job
from app.services.ingestion.qdrant_client import get_qdrant_client
from app.services.ingestion.embedding_processor import EmbeddingProcessor
from app.services.ingestion.indexers.youtube_transcript import date_facets


async def _youtube_targets(source_id: str | None) -> list[tuple[str, str, str]]:
    """Return (source_id, source_name, collection_name) for youtube sources.

    Skips any source with a queued/running index job so the backfill never
    races a concurrent (re)index that is writing the same chunks.
    """
    async with async_session_maker() as db:
        stmt = select(Source).where(
            Source.source_type == "youtube",
            Source.collection_name.isnot(None),
        )
        if source_id:
            stmt = stmt.where(Source.id == source_id)
        rows = (await db.execute(stmt)).scalars().all()

        targets = []
        for s in rows:
            busy = (await db.execute(
                select(Job).where(and_(
                    Job.job_type == "index_source",
                    Job.status.in_(["queued", "running"]),
                    Job.payload["source_id"].as_string() == s.id,
                ))
            )).scalar_one_or_none()
            if busy is not None:
                print(f"[SKIP] {s.name}: an index job is {busy.status}; "
                      f"re-run after it finishes to avoid racing the indexer.")
                continue
            targets.append((s.id, s.name, s.collection_name))
        return targets


def _backfill_collection(client, collection: str, source_id: str, dry_run: bool) -> dict:
    """Scroll a collection and merge date facets into each video's chunks.

    Scrolling is scoped to this source_id so the scan only touches the YouTube
    source's own chunks even if the collection is shared with other sources.
    """
    scroll_filter = models.Filter(
        must=[models.FieldCondition(
            key="source_id", match=models.MatchValue(value=source_id)
        )]
    )
    # Group point ids by video_id; capture one representative metadata per video.
    ids_by_video: dict[str, list] = defaultdict(list)
    meta_by_video: dict[str, dict] = {}
    offset = None
    scanned = 0
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=512,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            scanned += 1
            md = (p.payload or {}).get("metadata") or {}
            vid = md.get("video_id") or f"_noid_{p.id}"
            ids_by_video[vid].append(p.id)
            if vid not in meta_by_video:
                meta_by_video[vid] = md
        if offset is None:
            break

    updated_videos = 0
    updated_points = 0
    skipped_no_date = 0
    already = 0
    for vid, ids in ids_by_video.items():
        md = dict(meta_by_video.get(vid) or {})
        facets = date_facets(md.get("upload_date"))
        if not facets:
            skipped_no_date += 1
            continue
        if all(md.get(k) == v for k, v in facets.items()):
            already += 1
            continue
        if not dry_run:
            # Targeted nested write: set ONLY the 3 facet keys inside the
            # existing ``metadata`` object (qdrant-client >=1.8 `key=` param).
            # This merges rather than replacing metadata, so it cannot clobber
            # other/newer fields and does not assume all chunks of a video
            # share identical metadata.
            client.set_payload(
                collection_name=collection,
                payload=facets,
                key="metadata",
                points=ids,
            )
        updated_videos += 1
        updated_points += len(ids)

    return {
        "scanned_points": scanned,
        "videos": len(ids_by_video),
        "updated_videos": updated_videos,
        "updated_points": updated_points,
        "already_tagged": already,
        "skipped_no_date": skipped_no_date,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", default=None, help="Limit to one source id")
    ap.add_argument("--dry-run", action="store_true", help="Report only; no writes")
    args = ap.parse_args()

    client = get_qdrant_client()
    processor = EmbeddingProcessor()
    targets = await _youtube_targets(args.source_id)
    if not targets:
        print("No eligible YouTube sources (none found, or all have a running index job).")
        return

    for _sid, name, coll in targets:
        stats = _backfill_collection(client, coll, _sid, args.dry_run)
        if not args.dry_run:
            # Ensure the new published_* payload indexes exist on this collection.
            processor._create_keyword_indexes(coll)
        print(f"[{'DRY' if args.dry_run else 'DONE'}] {name} ({coll}): {stats}")


if __name__ == "__main__":
    asyncio.run(main())
