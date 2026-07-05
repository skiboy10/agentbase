"""YouTube channel transcript indexer (#133).

One ``source_type="youtube"`` source = one channel. ``source.source_path`` holds
the channel URL; ``youtube_backfill_mode`` / ``youtube_recent_count`` control how
much of the back catalogue to ingest.

Unlike :class:`UrlIndexer`, this indexer is **incremental by construction**:

- It NEVER clears ``IndexingLog`` at the start of a run — the log is the
  "already ingested" ledger. Each run enumerates the channel, diffs against the
  ledger, and only fetches videos that are new (or previously failed).
- It NEVER recreates the Qdrant collection (``_ensure_collection_exists`` only)
  so vectors from prior runs survive every delta.

That is what makes automatic freshness cheap: the refresh scheduler re-runs the
same ``index_source`` job daily, and a run with nothing new does almost nothing.

Transcripts are fetched with ``yt-dlp`` (validated by the #133 spike). Videos
without captions are recorded ``skipped``; a rate-limit/anti-bot block aborts the
run cleanly (partial progress preserved) so the next scheduled cycle resumes.
"""
import asyncio
import hashlib
import os
import sys
import tempfile
from datetime import datetime, timedelta
from glob import glob
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
import structlog

from app.core.config import get_settings
from app.core.url_validator import validate_youtube_channel_url
from app.models import Source, IndexingLog, DocumentContent

from .base import BaseIndexer
from .youtube_transcript import clean_vtt, rank_vtt_path, looks_like_block, date_facets

logger = structlog.get_logger()
settings = get_settings()

# yt-dlp invocation timeouts
ENUMERATE_TIMEOUT = 600.0   # listing a full channel (yt-dlp --flat-playlist)
PER_VIDEO_TIMEOUT = 120.0   # fetching one video's captions
SLEEP_BETWEEN_VIDEOS = 1.0  # politeness throttle (the #127/anti-bot lesson)

# Abort a wedged run rather than hang at status="indexing" forever (#127).
STALL_TIMEOUT = timedelta(minutes=15)


class _StallError(Exception):
    """No successful video in STALL_TIMEOUT — abort the run."""


class _BlockedError(Exception):
    """yt-dlp was rate-limited / anti-bot blocked. Pause and resume next cycle."""


class YouTubeIndexer(BaseIndexer):
    """Indexer for YouTube channel transcripts."""

    # ---------------------------------------------------------------- #
    # yt-dlp subprocess helpers
    # ---------------------------------------------------------------- #

    @staticmethod
    def _watch_url(video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"

    @staticmethod
    def _videos_url(channel_url: str) -> str:
        """Normalise a channel URL to its long-form uploads tab.

        Hitting ``/videos`` excludes Shorts and live tabs. Query strings and
        fragments (e.g. ``?si=...``) are dropped so the ``/videos`` suffix lands
        on the path rather than after the query. Idempotent.
        """
        parts = urlsplit(channel_url)
        path = parts.path.rstrip("/")
        if not path.endswith("/videos"):
            path = path + "/videos"
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    async def _run_ytdlp(self, args: list[str], timeout: float) -> tuple[int, str, str]:
        """Run yt-dlp as a subprocess; return (returncode, stdout, stderr).

        Invoked as ``python -m yt_dlp`` so it works regardless of console-script
        PATH inside the container. This uses the no-shell, list-argv spawn API
        (the safe equivalent of execFile): the channel URL and video IDs are
        passed as discrete argv elements and never interpolated into a shell
        string, so command injection is not possible.
        """
        spawn = asyncio.create_subprocess_exec  # no-shell, argv-list API
        cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--ignore-config",
               "--retries", "2", "--socket-timeout", "20", *args]
        proc = await spawn(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Reap on BOTH timeout and task cancellation so a killed/cancelled
            # index run never leaves an orphaned yt-dlp process (zombie/PID leak).
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            raise
        return (
            proc.returncode or 0,
            out.decode("utf-8", errors="replace"),
            err.decode("utf-8", errors="replace"),
        )

    async def _enumerate_videos(self, channel_url: str, limit: int | None) -> list[str]:
        """Return channel video IDs, newest first. Raises on block/failure."""
        args = ["--flat-playlist", "--print", "%(id)s"]
        if limit:
            args += ["--playlist-end", str(int(limit))]
        args.append(self._videos_url(channel_url))

        rc, out, err = await self._run_ytdlp(args, timeout=ENUMERATE_TIMEOUT)
        if rc != 0:
            if looks_like_block(err):
                raise _BlockedError(f"Blocked while enumerating channel: {err.strip()[:300]}")
            raise ValueError(f"yt-dlp could not enumerate channel: {err.strip()[:300]}")
        ids = [line.strip() for line in out.splitlines() if line.strip()]
        # De-dup while preserving order (channels occasionally repeat entries)
        seen: set[str] = set()
        return [v for v in ids if not (v in seen or seen.add(v))]

    async def _fetch_transcript(self, video_id: str, tmpdir: str) -> tuple[str | None, dict]:
        """Fetch one video's English captions.

        Returns ``(clean_text_or_None, metadata)``. ``None`` text means no
        captions were available (caller records the video as ``skipped``).
        Raises :class:`_BlockedError` on a rate-limit/anti-bot block.
        """
        watch_url = self._watch_url(video_id)
        out_tmpl = os.path.join(tmpdir, "%(id)s.%(ext)s")
        args = [
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", "en.*", "--sub-format", "vtt",
            # --print implies --simulate (no files written); --no-simulate
            # restores subtitle writing while still skipping the video download.
            "--no-simulate",
            "--print", "%(title)s\t%(upload_date)s\t%(duration)s",
            "-o", out_tmpl,
            watch_url,
        ]
        rc, out, err = await self._run_ytdlp(args, timeout=PER_VIDEO_TIMEOUT)
        if rc != 0:
            if looks_like_block(err):
                raise _BlockedError(f"Blocked fetching {video_id}: {err.strip()[:300]}")
            raise RuntimeError(err.strip()[:300] or "yt-dlp failed")

        meta = self._parse_meta(out, video_id)

        vtts = sorted(glob(os.path.join(tmpdir, f"{video_id}*.vtt")), key=rank_vtt_path)
        if not vtts:
            return None, meta

        try:
            with open(vtts[0], "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        finally:
            # Bound disk use across a large backfill — drop the files now.
            for path in vtts:
                try:
                    os.remove(path)
                except OSError:
                    pass

        return clean_vtt(raw) or None, meta

    @staticmethod
    def _parse_meta(stdout: str, video_id: str) -> dict:
        """Parse the tab-separated ``--print`` line into a metadata dict.

        Template is ``title\tupload_date\tduration``. A tab inside the title
        would shift positional parsing, so upload_date/duration (which the date
        facets depend on) are read from the END of the split; everything before
        them is rejoined as the title.
        """
        title, upload_date, duration = video_id, None, None
        for line in stdout.splitlines():
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 3:
                    duration = parts[-1].strip() or None
                    upload_date = parts[-2].strip() or None
                    title = "\t".join(parts[:-2]).strip() or video_id
                else:
                    title = parts[0].strip() or video_id
                    if len(parts) > 1:
                        upload_date = parts[1].strip() or None
                if upload_date in ("", "NA"):
                    upload_date = None
                if duration in ("", "NA"):
                    duration = None
                break
        return {"title": title, "upload_date": upload_date, "duration": duration}

    # ---------------------------------------------------------------- #
    # Ledger helpers
    # ---------------------------------------------------------------- #

    async def _load_logs(self, source_id: str) -> dict[str, IndexingLog]:
        """Load every IndexingLog row for the source once, keyed by watch URL.

        Bulk-loading up front avoids an N+1 SELECT per video on large backfills;
        new videos get their log created in-memory during the run.
        """
        stmt = select(IndexingLog).where(IndexingLog.source_id == source_id)
        result = await self.db.execute(stmt)
        return {log.url: log for log in result.scalars().all()}

    async def _backfill_kb_documents(self, source: Source, kbs: list) -> None:
        """Ensure every already-indexed video has a Document row in each bound library.

        Needed when a youtube source is bound to a library AFTER it was indexed
        standalone: the incremental loop skips done videos, so without this the
        library's Documents tab and stats would read empty. Rebuilds the rows
        from stored transcripts (``DocumentContent``) + per-video chunk counts
        (``IndexingLog``) — no network calls and no re-embedding. Idempotent.
        """
        if not kbs:
            return
        dc_rows = (await self.db.execute(
            select(DocumentContent).where(DocumentContent.source_id == source.id)
        )).scalars().all()
        if not dc_rows:
            return
        log_rows = (await self.db.execute(
            select(IndexingLog).where(IndexingLog.source_id == source.id)
        )).scalars().all()
        chunks_by_url = {log.url: (log.chunk_count or 0) for log in log_rows}

        for dc in dc_rows:
            await self._upsert_kb_documents(
                source=source, kbs=kbs,
                document_id=self._generate_document_id(source.id, dc.url),
                title=dc.title or dc.url,
                full_text=dc.raw_content or "",
                content_hash=dc.content_hash or "",
                url=dc.url,
                file_type="youtube",
                document_type="transcript",
                classification=None,
                chunk_count=chunks_by_url.get(dc.url, 0),
            )

    # ---------------------------------------------------------------- #
    # Main entry point
    # ---------------------------------------------------------------- #

    async def index(self, source: Source) -> None:
        """Incrementally index a YouTube channel's transcripts."""
        channel_url = source.source_path
        # Defense in depth — the create surface validates too.
        validate_youtube_channel_url(channel_url)

        mode = (source.youtube_backfill_mode or "recent").lower()
        limit = None if mode == "all" else (source.youtube_recent_count or 50)

        source.progress = 0
        source.progress_total = 0
        source.progress_message = "Enumerating channel videos..."
        source.progress_updated_at = datetime.utcnow()
        await self._publish_progress()

        video_ids = await self._enumerate_videos(channel_url, limit)
        total = len(video_ids)
        if total == 0:
            raise ValueError(
                "No videos found for this channel. Check the channel URL "
                "(expected something like https://www.youtube.com/@name)."
            )

        # Diff against the ledger — process new + previously-failed only.
        logs_by_url = await self._load_logs(source.id)
        todo = []
        for vid in video_ids:
            existing = logs_by_url.get(self._watch_url(vid))
            if existing is None or existing.status not in ("done", "skipped"):
                todo.append(vid)
        already_done = total - len(todo)

        source.progress_total = total
        source.progress = already_done
        source.progress_message = (
            f"{len(todo)} new of {total} videos to fetch..."
            if todo else f"Up to date — {total} videos already indexed."
        )
        source.progress_updated_at = datetime.utcnow()
        await self._publish_progress()

        # KB-aware setup — mirror UrlIndexer, but ensure-exists (never recreate).
        await self._load_kb_for_source(source)
        kbs = self._get_kbs(source)
        kb_aware = bool(kbs)
        primary_kb = kbs[0] if kbs else None

        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)
        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")
        await self._store_embedding_config(source, emb_provider, emb_model, vector_size)

        collection_name = self._get_collection_for_source(source)
        mirror_targets: list[tuple[str, str]] = self._get_library_mirror_collections(source)
        await self._ensure_collection_exists(collection_name, vector_size)
        for mirror_coll, _ in mirror_targets:
            await self._ensure_collection_exists(mirror_coll, vector_size)

        # Backfill Document rows for videos indexed in a prior standalone run so a
        # library bound after indexing shows correct Documents/stats (see method).
        if kb_aware:
            await self._backfill_kb_documents(source, kbs)

        text_splitter = self._get_text_splitter()

        new_docs = 0
        new_chunks = 0
        skipped = 0
        failed = 0
        blocked = False
        dimensions_captured = False
        last_progress_at = datetime.utcnow()

        logger.info(
            "Starting YouTube indexing",
            source_id=source.id, channel=channel_url, mode=mode,
            total=total, todo=len(todo), provider=emb_provider, model=emb_model,
            kb_aware=kb_aware,
        )

        with tempfile.TemporaryDirectory(prefix="yt_") as tmpdir:
            for idx, vid in enumerate(todo):
                if datetime.utcnow() - last_progress_at > STALL_TIMEOUT:
                    raise _StallError(
                        f"No successful video in {STALL_TIMEOUT.total_seconds() / 60:.0f} min — aborting"
                    )

                watch_url = self._watch_url(vid)
                log = logs_by_url.get(watch_url)
                if log is None:
                    log = IndexingLog(source_id=source.id, url=watch_url, status="pending")
                    self.db.add(log)
                    logs_by_url[watch_url] = log
                log.status = "fetching"
                log.error_message = None
                log.updated_at = datetime.utcnow()

                source.progress = already_done + idx
                source.progress_message = f"Fetching transcript {idx + 1}/{len(todo)}: {vid}"
                source.progress_updated_at = datetime.utcnow()
                await self._publish_progress()

                try:
                    text, meta = await self._fetch_transcript(vid, tmpdir)
                except _BlockedError as e:
                    # Pause the whole run; leave this video for next cycle.
                    log.status = "pending"
                    log.updated_at = datetime.utcnow()
                    await self.db.flush()
                    blocked = True
                    logger.warning(
                        "YouTube block encountered — pausing run, will resume next cycle",
                        source_id=source.id, video_id=vid, error=str(e),
                    )
                    break
                except (asyncio.TimeoutError, Exception) as e:
                    log.status = "failed"
                    log.error_message = str(e)[:500]
                    log.updated_at = datetime.utcnow()
                    failed += 1
                    last_progress_at = datetime.utcnow()  # making progress through the queue
                    await self.db.flush()
                    continue

                # Everything past the fetch is wrapped so a single bad video
                # (embedding error, DB hiccup) marks just that video failed and
                # the run still finalises cleanly — never hangs at "indexing".
                try:
                    title = meta.get("title") or vid

                    if not text or len(text.strip()) < 30:
                        log.status = "skipped"
                        log.error_message = "No captions available"
                        log.chunk_count = 0
                        log.updated_at = datetime.utcnow()
                        skipped += 1
                        last_progress_at = datetime.utcnow()
                        await self.db.flush()
                        continue

                    # Chunk + embed (reuse BaseIndexer machinery).
                    chunks = text_splitter.split_text(text)
                    log.content_length = len(text)
                    document_id = self._generate_document_id(source.id, watch_url) if kb_aware else None
                    scraped_at = datetime.utcnow().isoformat()

                    batch_chunks: list[str] = []
                    batch_metadata: list[dict] = []
                    for i, chunk in enumerate(chunks):
                        chunk_id = hashlib.md5(f"{watch_url}:{i}".encode()).hexdigest()
                        meta_row = {
                            "id": chunk_id,
                            "source": watch_url,
                            "source_id": source.id,
                            "chunk_index": i,
                            "title": title,
                            "scraped_at": scraped_at,
                            "metadata": {
                                "type": "transcript",
                                "video_id": vid,
                                "channel_url": channel_url,
                                "upload_date": meta.get("upload_date"),
                                "duration": meta.get("duration"),
                                # Filterable publish-date facets (year/month/int date)
                                **date_facets(meta.get("upload_date")),
                            },
                        }
                        if kb_aware and document_id and primary_kb:
                            meta_row["document_id"] = document_id
                            meta_row["library_id"] = primary_kb.id
                        batch_chunks.append(chunk)
                        batch_metadata.append(meta_row)

                    embedded = 0
                    for start in range(0, len(batch_chunks), self.BATCH_SIZE):
                        bc = batch_chunks[start:start + self.BATCH_SIZE]
                        bm = batch_metadata[start:start + self.BATCH_SIZE]
                        count, actual_dims = await self._process_embedding_batch(
                            collection_name, bc, bm, emb_provider, emb_model,
                            mirror_targets=mirror_targets or None,
                        )
                        embedded += count
                        if not dimensions_captured and actual_dims:
                            await self._update_embedding_dimensions(source, actual_dims)
                            dimensions_captured = True

                    # Persist raw transcript + KB Document row(s).
                    await self._save_scraped_content(
                        source=source, url=watch_url, title=title, content=text,
                    )
                    if kb_aware and document_id:
                        await self._upsert_kb_documents(
                            source=source, kbs=kbs, document_id=document_id,
                            title=title, full_text=text,
                            content_hash=self._compute_content_hash(text),
                            url=watch_url, file_type="youtube",
                            document_type="transcript", classification=None,
                            chunk_count=len(chunks),
                        )

                    log.status = "done"
                    log.chunk_count = len(chunks)
                    log.updated_at = datetime.utcnow()
                    new_docs += 1
                    new_chunks += embedded
                    last_progress_at = datetime.utcnow()
                    await self.db.flush()
                except Exception as e:
                    logger.warning(
                        "Failed to process video transcript",
                        source_id=source.id, video_id=vid, error=str(e),
                    )
                    log.status = "failed"
                    log.error_message = str(e)[:500]
                    log.updated_at = datetime.utcnow()
                    failed += 1
                    last_progress_at = datetime.utcnow()
                    await self.db.flush()
                    continue

                await asyncio.sleep(SLEEP_BETWEEN_VIDEOS)

        await self._finalize_youtube(source, total, new_docs, skipped, failed, blocked)

        logger.info(
            "YouTube indexing complete",
            source_id=source.id, total=total, new_docs=new_docs,
            new_chunks=new_chunks, skipped=skipped, failed=failed, blocked=blocked,
        )

    async def _finalize_youtube(
        self, source: Source, total: int, new_docs: int,
        skipped: int, failed: int, blocked: bool,
    ) -> None:
        """Set absolute totals from the ledger (delta-safe) and finalise status."""
        stmt = select(IndexingLog).where(
            IndexingLog.source_id == source.id, IndexingLog.status == "done"
        )
        result = await self.db.execute(stmt)
        done_logs = list(result.scalars().all())

        source.document_count = len(done_logs)
        source.chunk_count = sum((log.chunk_count or 0) for log in done_logs)
        source.last_indexed = datetime.utcnow()
        source.progress = source.progress_total or total
        source.progress_updated_at = datetime.utcnow()

        if source.document_count == 0 and total > 0:
            # Nothing landed despite videos existing — surface as error.
            source.status = "error"
            if blocked:
                source.error_message = (
                    "Rate-limited/blocked by YouTube before any transcript was "
                    "indexed. It will retry on the next refresh."
                )
            else:
                source.error_message = (
                    f"No transcripts indexed ({failed} failed, "
                    f"{skipped} had no captions)."
                )
            source.progress_message = f"Error: {source.error_message}"
        else:
            source.status = "indexed"
            source.error_message = None
            parts = [f"{source.document_count} videos indexed"]
            if new_docs:
                parts.append(f"{new_docs} new")
            if skipped:
                parts.append(f"{skipped} skipped (no captions)")
            if failed:
                parts.append(f"{failed} failed")
            if blocked:
                parts.append("paused on rate-limit (resumes next refresh)")
            source.progress_message = "Complete: " + ", ".join(parts)

        from app.services.freshness_service import compute_next_refresh_at
        source.next_refresh_at = compute_next_refresh_at(source)
        await self.db.flush()
