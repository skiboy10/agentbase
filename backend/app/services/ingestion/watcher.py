"""
Directory source watcher service.

Monitors directory-type knowledge sources for file changes and automatically
queues re-indexing when files are added, modified, or deleted.

Two watch modes:
  events  — watchdog OS-level filesystem events (efficient, low latency)
  polling — periodic directory scan with mtime comparison (reliable on
             network drives and containers where inotify may not work)
  auto    — starts in event mode; falls back to polling if no events are seen
             within 2× the poll_interval while the directory is non-empty.

Threading notes:
  - Watchdog delivers events on its own background thread.
  - _record_event() is the only method called from that thread; it uses
    threading.Lock to guard the shared _pending dict and writes only to
    simple scalars (GIL-protected for CPython).
  - All asyncio coroutines run on the event loop. Blocking I/O (file hashing,
    directory scanning, Qdrant sync client calls) is dispatched to the default
    ThreadPoolExecutor via asyncio.get_event_loop().run_in_executor so the
    event loop is never blocked.
"""

import asyncio
import hashlib
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.core.config import get_settings
from app.models import Source, ScrapedContent, WatcherEvent, Library, LibrarySource
from .background_tasks import reindex_file, run_indexing_task
from .qdrant_client import get_qdrant_client

logger = structlog.get_logger()
settings = get_settings()


# ---------------------------------------------------------------------------
# Root-health guard thresholds
# ---------------------------------------------------------------------------
# A reconcile cycle that would delete this fraction (or more) of the indexed
# set, on an index at least this large, is treated as an anomaly (a broken
# mount / unmounted root) rather than a legitimate bulk delete. The watcher
# halts with watch_status="error" instead of issuing the deletions.
WATCH_ROOT_MASS_DELETE_FRACTION = 0.90
WATCH_ROOT_MASS_DELETE_MIN = 50


def _is_mass_deletion(indexed_count: int, deleted_count: int) -> bool:
    """True when a single reconcile cycle would wipe a suspicious share of the index.

    Guards the failure mode where an unmounted/renamed watch root scans as empty
    and every indexed file looks deleted. Small indexes (< WATCH_ROOT_MASS_DELETE_MIN)
    are never guarded so ordinary cleanup of a tiny source isn't blocked.
    """
    if indexed_count < WATCH_ROOT_MASS_DELETE_MIN:
        return False
    return deleted_count >= WATCH_ROOT_MASS_DELETE_FRACTION * indexed_count


# ---------------------------------------------------------------------------
# Blocking I/O helpers (called via run_in_executor — never on the event loop)
# ---------------------------------------------------------------------------

def _probe_root_health_sync(root: Path) -> tuple[str, Optional[str]]:
    """Classify a watch root before trusting a directory scan.

    Returns (status, detail):
      "ok"          - root exists, is a directory, and is listable
      "missing"     - root path does not exist
      "unreadable"  - root exists but cannot be listed (broken bind mount,
                      permission loss, network-drive disconnect). os.scandir
                      raises OSError (ENOTCONN/EPERM/EIO) here, which os.walk
                      would otherwise swallow into a misleading empty result.

    The "unreadable" case is the dangerous one: a Docker bind mount whose host
    source was renamed/removed leaves an empty-but-present mountpoint, so
    Path.is_dir() still returns True while every file appears to have vanished.
    Synchronous blocking I/O — call via run_in_executor off the event loop.
    """
    try:
        if not root.exists():
            return ("missing", f"Watch root does not exist: {root}")
        if not root.is_dir():
            return ("unreadable", f"Watch root is not a directory: {root}")
        with os.scandir(root) as it:
            next(it, None)  # force a real read; broken mounts raise here
    except OSError as exc:
        return ("unreadable", f"Watch root is unreadable: {root} ({exc})")
    return ("ok", None)

def _compute_file_hash_sync(path: Path) -> Optional[str]:
    """SHA-256 hash of file bytes. Returns None if file is unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def _scan_directory_sync(
    root: Path,
    extensions: list[str],
    max_depth: int,
    max_size_mb: int,
    path_excludes: Optional[list[str]] = None,
) -> dict[str, float]:
    """
    Walk directory up to max_depth, applying extension, size, and exclude filters.

    Returns mapping of absolute file path → mtime (float).
    This is synchronous blocking I/O; always call via run_in_executor.

    ``path_excludes`` is a list of canonical POSIX prefixes (typically from
    ``Source.path_excludes``). Any file whose path is under an excluded prefix
    is skipped; directories whose path matches are pruned from the walk.
    """
    result: dict[str, float] = {}
    max_bytes = max_size_mb * 1024 * 1024
    ext_set = {e.lower() for e in extensions} if extensions else None

    # Pre-normalise excludes once (caller may pass raw user input)
    from .path_utils import canonicalise_path
    norm_excludes = [canonicalise_path(e) for e in (path_excludes or []) if e]

    def _under_any_exclude(p: Path) -> bool:
        if not norm_excludes:
            return False
        c = canonicalise_path(p)
        for ex in norm_excludes:
            if c == ex or c.startswith(ex.rstrip("/") + "/"):
                return True
        return False

    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth >= max_depth:
            dirnames.clear()  # Don't recurse deeper
            continue

        # Prune excluded subdirectories in-place so os.walk doesn't descend.
        if norm_excludes:
            dirnames[:] = [
                d for d in dirnames if not _under_any_exclude(Path(dirpath) / d)
            ]

        for fname in filenames:
            fp = Path(dirpath) / fname
            if ext_set and fp.suffix.lower() not in ext_set:
                continue
            if _under_any_exclude(fp):
                continue
            try:
                stat = fp.stat()
                if stat.st_size > max_bytes:
                    continue
                result[str(fp)] = stat.st_mtime
            except OSError:
                continue

    return result


def _delete_qdrant_vectors_sync(collection_name: str, file_path: str) -> None:
    """
    Remove Qdrant points whose payload 'source' matches file_path.
    Uses the synchronous QdrantClient — must be run in an executor.
    """
    try:
        client = get_qdrant_client()
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=file_path),
                    )
                ]
            ),
        )
        logger.debug("Deleted Qdrant vectors", collection=collection_name, file=file_path)
    except Exception as exc:
        logger.warning("Failed to delete Qdrant vectors", file=file_path, error=str(exc))


# ---------------------------------------------------------------------------
# Async wrappers for blocking helpers
# ---------------------------------------------------------------------------

async def _compute_file_hash(path: Path) -> Optional[str]:
    """Async wrapper: hash file bytes in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _compute_file_hash_sync, path)


async def _scan_directory(
    root: Path,
    extensions: list[str],
    max_depth: int,
    max_size_mb: int,
    path_excludes: Optional[list[str]] = None,
) -> dict[str, float]:
    """Async wrapper: scan directory in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _scan_directory_sync, root, extensions, max_depth, max_size_mb, path_excludes
    )


async def _delete_vectors_for_file(collection_name: str, file_path: str) -> None:
    """Async wrapper: delete Qdrant vectors in thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _delete_qdrant_vectors_sync, collection_name, file_path
    )


async def _probe_root_health(root: Path) -> tuple[str, Optional[str]]:
    """Async wrapper: classify watch-root health in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _probe_root_health_sync, root)


# ---------------------------------------------------------------------------
# Database helpers (fully async — use these on the event loop directly)
# ---------------------------------------------------------------------------

async def _delete_scraped_record(db: AsyncSession, source_id: str, file_path: str) -> None:
    """Delete ScrapedContent record keyed by file_path stored in the url column."""
    try:
        stmt = select(ScrapedContent).where(
            ScrapedContent.source_id == source_id,
            ScrapedContent.url == file_path,
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if record:
            await db.delete(record)
            await db.flush()
    except Exception as exc:
        logger.warning("Failed to delete scraped record", file=file_path, error=str(exc))


async def _resolve_target_collections(
    db: AsyncSession, source_id: str, source_collection: Optional[str]
) -> list[str]:
    """Return every Qdrant collection a directory source's chunks live in.

    Mirrors ``BaseIndexer._get_collections_for_source``: the source's own
    collection (``source_collection``) holds the primary copy the RAG read path
    queries; each bound library's collection holds a mirror. Deletions MUST
    target all of them, or vectors for deleted files leak in the collection RAG
    actually reads.
    """
    stmt = (
        select(Library.collection_name)
        .join(LibrarySource, LibrarySource.library_id == Library.id)
        .where(LibrarySource.source_id == source_id)
    )
    library_collections = [c for c in (await db.execute(stmt)).scalars().all() if c]
    result = [source_collection] if source_collection else []
    result.extend(library_collections)
    return result


async def _get_indexed_file_hashes(db: AsyncSession, source_id: str) -> dict[str, str]:
    """Return {file_path: content_hash} from ScrapedContent for a source."""
    stmt = select(ScrapedContent).where(ScrapedContent.source_id == source_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    # url column stores file_path for directory sources
    return {r.url: r.content_hash for r in rows}


async def _emit_event(
    source_id: str,
    event_type: str,
    severity: str = "info",
    file_path: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    """Insert a WatcherEvent row. Fire-and-forget — never raises."""
    try:
        async with async_session_maker() as db:
            # WatcherEvent.timestamp is TIMESTAMP WITHOUT TIME ZONE; strip tzinfo
            # to keep asyncpg's binder happy. Compute the UTC instant first so
            # the stored value remains UTC-consistent.
            event = WatcherEvent(
                id=str(uuid.uuid4()),
                source_id=source_id,
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                event_type=event_type,
                file_path=file_path,
                severity=severity,
                message=message,
            )
            db.add(event)
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to emit watcher event", source_id=source_id, event_type=event_type, error=str(exc))


async def _update_source_status(
    source_id: str,
    watch_status: str,
    watch_last_heartbeat_at: Optional[datetime] = None,
    watch_last_error: Optional[str] = None,
) -> None:
    """Update watch_status (and optionally heartbeat/error) on a Source. Never raises."""
    try:
        async with async_session_maker() as db:
            stmt = select(Source).where(Source.id == source_id)
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()
            if source:
                source.watch_status = watch_status
                if watch_last_heartbeat_at is not None:
                    # Source.watch_last_heartbeat_at column is naive UTC; strip tzinfo
                    source.watch_last_heartbeat_at = (
                        watch_last_heartbeat_at.replace(tzinfo=None)
                        if watch_last_heartbeat_at.tzinfo
                        else watch_last_heartbeat_at
                    )
                if watch_last_error is not None:
                    source.watch_last_error = watch_last_error
                await db.commit()
    except Exception as exc:
        logger.warning("Failed to update source watch_status", source_id=source_id, error=str(exc))


# ---------------------------------------------------------------------------
# Watchdog event handler (runs in a watchdog thread — must be thread-safe)
# ---------------------------------------------------------------------------

class _AgentbaseEventHandler:
    """
    Adapter between watchdog callbacks (sync thread) and the watcher's
    async debounce buffer.  Writes only to _pending (protected by _pending_lock).
    """

    def __init__(self, watcher: "DirectoryWatcher"):
        self._watcher = watcher

    def on_created(self, event):
        if not event.is_directory:
            self._watcher._record_event(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._watcher._record_event(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory:
            self._watcher._record_event(event.src_path, "deleted")

    def on_moved(self, event):
        if not event.is_directory:
            self._watcher._record_event(event.src_path, "deleted")
            self._watcher._record_event(event.dest_path, "created")


# ---------------------------------------------------------------------------
# DirectoryWatcher
# ---------------------------------------------------------------------------

class DirectoryWatcher:
    """
    Watches a single directory knowledge source for file changes.

    Lifecycle:
        watcher = DirectoryWatcher(source_id, path, config)
        await watcher.start()
        ...
        await watcher.stop()
    """

    def __init__(self, source_id: str, path: str, config: dict):
        self.source_id = source_id
        self.path = Path(path)
        self.extensions: list[str] = config.get("watch_extensions") or []
        self.max_file_size_mb: int = config.get("watch_max_file_size_mb", 50)
        self.debounce_seconds: int = config.get("watch_debounce_seconds", 60)
        self.max_depth: int = config.get("watch_depth", 10)
        self.mode: str = config.get("watch_mode", "auto")
        self.poll_interval: int = config.get("watch_poll_interval_seconds", 300)
        self.collection_name: str = config.get("collection_name", "")
        # Canonical exclude prefixes — applied to event stream and polling scan.
        from .path_utils import canonicalise_path
        self.path_excludes: list[str] = [
            canonicalise_path(e) for e in (config.get("path_excludes") or []) if e
        ]

        # Internal state
        self._running = False
        self._error_halted = False  # tripped the root-health guard; needs manual resync
        self._event_mode_active = False
        self._last_event_time: Optional[float] = None  # wall-clock seconds (time.time())
        self._event_count = 0
        self._started_at: Optional[datetime] = None

        # Pending events: {file_path: (event_type, received_monotonic)}
        # Written from watchdog thread (under _pending_lock); read from asyncio loop.
        self._pending: dict[str, tuple[str, float]] = {}
        self._pending_lock = threading.Lock()

        # Tracked asyncio tasks (stored so they can be cancelled on stop)
        self._poll_task: Optional[asyncio.Task] = None
        self._debounce_task: Optional[asyncio.Task] = None
        self._auto_task: Optional[asyncio.Task] = None

        self._watchdog_observer = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start watching. Chooses event-based or polling based on config."""
        if self._running:
            return

        if not self.path.exists():
            logger.warning(
                "Watch path does not exist, skipping",
                path=str(self.path),
                source_id=self.source_id,
            )
            return

        self._running = True
        self._started_at = datetime.now(timezone.utc)

        effective_mode = self.mode
        if effective_mode in ("events", "auto"):
            started = self._start_watchdog()
            self._event_mode_active = started
            if not started:
                effective_mode = "polling"

        if effective_mode == "polling" or (self.mode == "auto" and not self._event_mode_active):
            self._poll_task = asyncio.create_task(self._poll_loop())

        if self._event_mode_active:
            self._debounce_task = asyncio.create_task(self._drain_debounce_loop())
            if self.mode == "auto":
                self._auto_task = asyncio.create_task(self._auto_mode_watchdog())

        logger.info(
            "Watcher started",
            source_id=self.source_id,
            path=str(self.path),
            mode="events" if self._event_mode_active else "polling",
        )
        asyncio.create_task(_emit_event(self.source_id, "started", message=f"mode={'events' if self._event_mode_active else 'polling'}"))
        # Clear any prior error on a (re)start — a manual start is the resync.
        asyncio.create_task(_update_source_status(self.source_id, "running", watch_last_heartbeat_at=datetime.now(timezone.utc), watch_last_error=""))

    async def stop(self) -> None:
        """Stop watching gracefully."""
        self._running = False

        # Stop watchdog observer (blocks briefly in the calling thread)
        if self._watchdog_observer is not None:
            try:
                self._watchdog_observer.stop()
                self._watchdog_observer.join(timeout=5)
            except Exception as exc:
                logger.warning("Error stopping watchdog observer", error=str(exc))
            self._watchdog_observer = None

        # Cancel all tracked asyncio tasks
        for task_attr in ("_poll_task", "_debounce_task", "_auto_task"):
            task: Optional[asyncio.Task] = getattr(self, task_attr)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            setattr(self, task_attr, None)

        logger.info("Watcher stopped", source_id=self.source_id)
        asyncio.create_task(_emit_event(self.source_id, "stopped"))
        asyncio.create_task(_update_source_status(self.source_id, "stopped"))

    @property
    def status(self) -> dict:
        """Return current watcher state for monitoring."""
        return {
            "source_id": self.source_id,
            "path": str(self.path),
            "running": self._running,
            "mode": "events" if self._event_mode_active else "polling",
            "last_event": self._last_event_time,
            "event_count": self._event_count,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "error_halted": self._error_halted,
        }

    # ------------------------------------------------------------------
    # Root-health guard
    # ------------------------------------------------------------------

    async def _trip_root_guard(self, reason: str) -> None:
        """Halt the watcher on a root-health anomaly without emitting deletions.

        Sets watch_status="error" and stops all activity. The supervisor will
        NOT auto-restart a watcher in the error state — recovery is manual
        (fix the source, then start the watcher / force-sync / re-index).
        """
        logger.error("Watcher root guard tripped — halting", source_id=self.source_id, reason=reason)
        self._error_halted = True
        self._running = False

        # Stop the watchdog observer thread if we were in event mode, so it
        # can't keep buffering phantom delete events while we're halted.
        if self._watchdog_observer is not None:
            try:
                self._watchdog_observer.stop()
                self._watchdog_observer.join(timeout=5)
            except Exception as exc:
                logger.warning("Error stopping observer on guard trip", error=str(exc))
            self._watchdog_observer = None

        asyncio.create_task(_emit_event(self.source_id, "error", severity="error", message=reason))
        asyncio.create_task(_update_source_status(self.source_id, "error", watch_last_error=reason))

    # ------------------------------------------------------------------
    # Event recording (called from watchdog thread — thread-safe)
    # ------------------------------------------------------------------

    def _record_event(self, file_path: str, event_type: str) -> None:
        """
        Buffer an incoming filesystem event for debounced async processing.

        Called from the watchdog background thread. Only touches:
        - self.extensions, self.max_file_size_mb, self.path_excludes: read-only
          after __init__ (safe)
        - self._pending: guarded by self._pending_lock
        - self._last_event_time, self._event_count: simple scalar writes (GIL-safe)
        """
        fp = Path(file_path)

        # Extension filter
        if self.extensions and fp.suffix.lower() not in {e.lower() for e in self.extensions}:
            return

        # Exclude-path filter — drop early so we don't dispatch reindex tasks
        # for files the caller has explicitly told us to ignore.
        if self.path_excludes:
            from .path_utils import canonicalise_path
            canon = canonicalise_path(file_path)
            for ex in self.path_excludes:
                if canon == ex or canon.startswith(ex.rstrip("/") + "/"):
                    return

        # Size filter (skip for deleted events — file may already be gone)
        if event_type != "deleted":
            try:
                size_mb = fp.stat().st_size / (1024 * 1024)
                if size_mb > self.max_file_size_mb:
                    logger.debug("Skipping oversized file", file=file_path, size_mb=size_mb)
                    return
            except OSError:
                return

        now = time.monotonic()
        with self._pending_lock:
            # Later event type wins within the debounce window
            self._pending[file_path] = (event_type, now)

        # Simple scalar writes — safe under CPython GIL without a lock
        self._last_event_time = time.time()
        self._event_count += 1

    # ------------------------------------------------------------------
    # Watchdog startup
    # ------------------------------------------------------------------

    def _start_watchdog(self) -> bool:
        """Start the watchdog OS observer. Returns True on success."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, adapter: _AgentbaseEventHandler):
                    self._adapter = adapter

                def on_created(self, event):
                    self._adapter.on_created(event)

                def on_modified(self, event):
                    self._adapter.on_modified(event)

                def on_deleted(self, event):
                    self._adapter.on_deleted(event)

                def on_moved(self, event):
                    self._adapter.on_moved(event)

            handler = _AgentbaseEventHandler(self)
            observer = Observer()
            observer.schedule(_Handler(handler), str(self.path), recursive=True)
            observer.start()
            self._watchdog_observer = observer
            return True
        except Exception as exc:
            logger.warning("Failed to start watchdog observer, using polling", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Event mode: debounce drain loop
    # ------------------------------------------------------------------

    async def _drain_debounce_loop(self) -> None:
        """Drain the pending-events buffer after each file's debounce window expires."""
        check_interval = max(5, self.debounce_seconds // 4)
        while self._running:
            await asyncio.sleep(check_interval)
            if not self._pending:
                continue

            now = time.monotonic()
            ready: list[tuple[str, str]] = []
            with self._pending_lock:
                for file_path, (ev_type, received_at) in list(self._pending.items()):
                    if now - received_at >= self.debounce_seconds:
                        ready.append((file_path, ev_type))
                        del self._pending[file_path]

            for file_path, ev_type in ready:
                if not self._running:
                    break  # guard tripped mid-batch — stop processing
                await self._handle_event(file_path, ev_type)

    async def _handle_event(self, file_path: str, event_type: str) -> None:
        """Process a single debounced file event."""
        # Never honour a deletion while the root itself is unhealthy — an
        # unmounted/renamed root surfaces as a flood of phantom deletes.
        if event_type == "deleted":
            health, detail = await _probe_root_health(self.path)
            if health != "ok":
                await self._trip_root_guard(
                    detail or f"Watch root unhealthy, refusing deletion: {self.path}"
                )
                return

        logger.info("Processing file event", event_type=event_type, file=file_path, source_id=self.source_id)
        asyncio.create_task(_emit_event(self.source_id, event_type, file_path=file_path))
        async with async_session_maker() as db:
            try:
                if event_type == "deleted":
                    await self._handle_delete(db, file_path)
                    await db.commit()
                elif event_type in ("created", "modified"):
                    await self._handle_upsert(db, file_path, event_type)
                    await db.commit()
            except Exception as exc:
                logger.error(
                    "Error handling file event",
                    event=event_type,
                    file=file_path,
                    error=str(exc),
                )
                asyncio.create_task(_emit_event(self.source_id, "error", severity="error", file_path=file_path, message=str(exc)))
                await db.rollback()

    async def _handle_delete(self, db: AsyncSession, file_path: str) -> None:
        """Delete Qdrant vectors and DB record for a removed file.

        Vectors are removed from every collection the source writes to (its
        bound libraries' collections, or its own when unbound) — keyed by the
        same root-relative path the indexer stores in the ``source`` payload.
        """
        root_rel = self._relative_path(file_path)
        collections = await _resolve_target_collections(db, self.source_id, self.collection_name)
        for coll in collections:
            await _delete_vectors_for_file(coll, root_rel)
        await _delete_scraped_record(db, self.source_id, file_path)
        logger.info("Handled delete", file=file_path, source_id=self.source_id, collections=collections)

    async def _handle_upsert(self, db: AsyncSession, file_path: str, event_type: str) -> None:
        """Queue a single-file re-index, skipping if content hash is unchanged.

        Previously this triggered a full-source re-index which re-embedded
        every file in the tree on any change (catastrophic on large sources).
        Now it dispatches the per-file ``reindex_file`` task, which deletes
        just this file's chunks and re-embeds them. ``FileItemIndexer.index_one``
        does its own content-hash short-circuit, so we don't pre-filter here.
        """
        fp = Path(file_path)
        if not fp.exists():
            # File disappeared between event and processing; treat as delete
            await self._handle_delete(db, file_path)
            return

        new_hash = await _compute_file_hash(fp)
        if new_hash is None:
            logger.warning("Cannot read file, skipping", file=file_path)
            return

        # Fast pre-check: if we already have the same hash, don't bother dispatching.
        if event_type == "modified":
            indexed = await _get_indexed_file_hashes(db, self.source_id)
            stored_hash = indexed.get(file_path)
            if stored_hash and stored_hash == new_hash:
                logger.debug("File unchanged (hash match), skipping", file=file_path)
                return

        # Per-file re-index via background task — fans out to bound libraries
        # and updates the per-source DocumentContent row.
        asyncio.create_task(reindex_file(self.source_id, file_path))

    def _relative_path(self, file_path: str) -> str:
        """Return path relative to watch root, or absolute if outside root."""
        try:
            return str(Path(file_path).relative_to(self.path))
        except ValueError:
            return file_path

    # ------------------------------------------------------------------
    # Auto-mode: fall back to polling if events go silent
    # ------------------------------------------------------------------

    async def _auto_mode_watchdog(self) -> None:
        """
        Auto-mode health check: switch to polling if no events are seen for
        2× poll_interval while the directory contains matching files.
        """
        threshold = self.poll_interval * 2
        await asyncio.sleep(threshold)

        if not self._running or not self._event_mode_active:
            return

        has_files = bool(
            await _scan_directory(self.path, self.extensions, self.max_depth, self.max_file_size_mb, self.path_excludes)
        )
        no_recent_event = (
            self._last_event_time is None
            or (time.time() - self._last_event_time) > threshold
        )

        if has_files and no_recent_event:
            logger.info(
                "Auto-mode: no events detected, switching to polling",
                source_id=self.source_id,
            )
            self._event_mode_active = False
            if self._watchdog_observer:
                try:
                    self._watchdog_observer.stop()
                    self._watchdog_observer.join(timeout=5)
                except Exception:
                    pass
                self._watchdog_observer = None

            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()
                try:
                    await self._debounce_task
                except asyncio.CancelledError:
                    pass
                self._debounce_task = None

            self._poll_task = asyncio.create_task(self._poll_loop())

    # ------------------------------------------------------------------
    # Polling mode
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Periodic directory scan comparing disk vs indexed state."""
        previous_snapshot: dict[str, float] = {}

        while self._running:
            await asyncio.sleep(self.poll_interval)
            if not self._running:
                break

            try:
                # Root-health guard: an unmounted/renamed root scans as empty
                # via os.walk (it swallows the OSError), which would otherwise
                # be read as "every indexed file was deleted".
                health, detail = await _probe_root_health(self.path)
                if health != "ok":
                    await self._trip_root_guard(
                        detail or f"Watch root unhealthy: {self.path}"
                    )
                    break

                current_snapshot = await _scan_directory(
                    self.path, self.extensions, self.max_depth, self.max_file_size_mb,
                    self.path_excludes,
                )
                async with async_session_maker() as db:
                    indexed = await _get_indexed_file_hashes(db, self.source_id)

                new_files = set(current_snapshot) - set(indexed)
                deleted_files = set(indexed) - set(current_snapshot)
                candidate_modified = set(current_snapshot) & set(indexed)

                # Mass-deletion safety valve: even with a readable root, refuse
                # to act on a single cycle that would wipe most of the index
                # (e.g. a momentarily-empty mount). Halt for manual resync.
                if _is_mass_deletion(len(indexed), len(deleted_files)):
                    await self._trip_root_guard(
                        f"Refusing mass deletion: {len(deleted_files)}/{len(indexed)} indexed "
                        f"files disappeared from {self.path} in one scan. Watcher halted "
                        f"(watch_status=error). If the source is broken (e.g. unmounted), fix it "
                        f"then restart the watcher to resume. If this bulk removal was intended, "
                        f"run force-sync with allow_mass_delete=true."
                    )
                    break

                modified_files: list[str] = []
                for fp_str in candidate_modified:
                    if fp_str in previous_snapshot:
                        if current_snapshot[fp_str] != previous_snapshot[fp_str]:
                            modified_files.append(fp_str)

                if new_files or deleted_files or modified_files:
                    logger.info(
                        "Polling detected changes",
                        source_id=self.source_id,
                        new=len(new_files),
                        deleted=len(deleted_files),
                        modified=len(modified_files),
                    )
                    self._event_count += len(new_files) + len(deleted_files) + len(modified_files)
                    self._last_event_time = time.time()

                    for fp_str in deleted_files:
                        self._record_event(fp_str, "deleted")
                    for fp_str in new_files:
                        self._record_event(fp_str, "created")
                    for fp_str in modified_files:
                        self._record_event(fp_str, "modified")

                    # Wait the debounce window, then drain
                    await asyncio.sleep(self.debounce_seconds)
                    now = time.monotonic()
                    ready: list[tuple[str, str]] = []
                    with self._pending_lock:
                        for file_path, (ev_type, received_at) in list(self._pending.items()):
                            if now - received_at >= self.debounce_seconds:
                                ready.append((file_path, ev_type))
                                del self._pending[file_path]
                    for file_path, ev_type in ready:
                        if not self._running:
                            break  # guard tripped mid-batch — stop processing
                        await self._handle_event(file_path, ev_type)

                previous_snapshot = current_snapshot

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Polling loop error", source_id=self.source_id, error=str(exc))


# ---------------------------------------------------------------------------
# WatcherManager
# ---------------------------------------------------------------------------

class WatcherManager:
    """
    Manages DirectoryWatcher instances for all knowledge sources with
    watch_enabled=True.

    Usage (called from app lifespan):
        manager = WatcherManager()
        await manager.start_all()   # app startup
        ...
        await manager.stop_all()    # app shutdown
    """

    def __init__(self):
        self._watchers: dict[str, DirectoryWatcher] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Start watchers for all root directory sources with watch_enabled=True.

        Sub-sources (parent_source_id IS NOT NULL) are filtered out — they
        share the parent root's watcher and don't run their own observer.
        """
        async with async_session_maker() as db:
            stmt = select(Source).where(
                Source.source_type == "directory",
                Source.watch_enabled == True,  # noqa: E712
                Source.parent_source_id.is_(None),
            )
            result = await db.execute(stmt)
            sources = result.scalars().all()

        logger.info("Starting directory watchers", count=len(sources))
        for source in sources:
            try:
                await self.start_watcher(source.id)
            except Exception as exc:
                logger.error("Failed to start watcher", source_id=source.id, error=str(exc))

    async def stop_all(self) -> None:
        """Gracefully stop all active watchers."""
        source_ids = list(self._watchers.keys())
        for source_id in source_ids:
            try:
                await self.stop_watcher(source_id)
            except Exception as exc:
                logger.error("Failed to stop watcher", source_id=source_id, error=str(exc))

    # ------------------------------------------------------------------
    # Per-source control
    # ------------------------------------------------------------------

    async def start_watcher(self, source_id: str) -> None:
        """Start a watcher for a specific knowledge source."""
        existing = self._watchers.get(source_id)
        if existing is not None:
            if getattr(existing, "_error_halted", False):
                # Manual resync: discard the halted instance and recreate below.
                logger.info("Replacing error-halted watcher on manual start", source_id=source_id)
                self._watchers.pop(source_id, None)
            else:
                logger.debug("Watcher already running", source_id=source_id)
                return

        async with async_session_maker() as db:
            stmt = select(Source).where(Source.id == source_id)
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()

        if not source:
            raise ValueError(f"Source not found: {source_id}")
        if source.source_type != "directory":
            raise ValueError(f"Source {source_id} is not a directory type")
        if getattr(source, "parent_source_id", None):
            raise ValueError(
                f"Source {source_id} is a sub-source; start the parent root's watcher instead"
            )
        if not source.watch_enabled:
            logger.info("watch_enabled=False, not starting watcher", source_id=source_id)
            return

        config = {
            "watch_extensions": source.watch_extensions or [],
            "watch_max_file_size_mb": source.watch_max_file_size_mb,
            "watch_debounce_seconds": source.watch_debounce_seconds,
            "watch_depth": source.watch_depth,
            "watch_mode": source.watch_mode,
            "watch_poll_interval_seconds": source.watch_poll_interval_seconds,
            "collection_name": source.collection_name or "",
            "path_excludes": source.path_excludes or [],
        }

        watcher = DirectoryWatcher(source_id, source.source_path, config)
        self._watchers[source_id] = watcher
        await watcher.start()

    async def stop_watcher(self, source_id: str) -> None:
        """Stop watcher for a specific knowledge source."""
        watcher = self._watchers.pop(source_id, None)
        if watcher:
            await watcher.stop()
        else:
            logger.debug("No watcher running for source", source_id=source_id)

    # ------------------------------------------------------------------
    # Supervisor loop
    # ------------------------------------------------------------------

    async def supervise_forever(self) -> None:
        """Long-lived supervisor task — restarts watchers that have died. Never exits."""
        while True:
            try:
                await self.supervise()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Supervisor loop error", error=str(exc))
            await asyncio.sleep(60)

    async def supervise(self) -> None:
        """
        One supervision tick:
        - Start any enabled watcher not currently running.
        - Restart dead watchdog observers.
        - Stop watchers whose sources are no longer watch_enabled.
        - Update watch_status + heartbeat for healthy watchers.
        - Set watch_status=path_missing and stop when path is gone.
        """
        async with async_session_maker() as db:
            stmt = select(Source).where(
                Source.source_type == "directory",
                Source.parent_source_id.is_(None),
            )
            result = await db.execute(stmt)
            all_dir_sources = result.scalars().all()

        for source in all_dir_sources:
            source_id = source.id
            try:
                if not source.watch_enabled:
                    if source_id in self._watchers:
                        logger.info("Supervisor: stopping disabled watcher", source_id=source_id)
                        await self.stop_watcher(source_id)
                        asyncio.create_task(_emit_event(source_id, "stopped", message="watch_enabled set to False"))
                    continue

                # Error-halted watchers (root-health guard tripped) require a
                # manual resync. Do NOT auto-restart; drop any halted instance
                # so a later manual start_watcher can recreate it cleanly.
                if source.watch_status == "error":
                    halted = self._watchers.pop(source_id, None)
                    if halted is not None:
                        logger.info("Supervisor: leaving error-halted watcher idle", source_id=source_id)
                    continue

                path_exists = Path(source.source_path).is_dir()
                if not path_exists:
                    if source_id in self._watchers:
                        await self.stop_watcher(source_id)
                    asyncio.create_task(_update_source_status(source_id, "path_missing", watch_last_error=f"Path not found: {source.source_path}"))
                    asyncio.create_task(_emit_event(source_id, "error", severity="error", message=f"Path not found: {source.source_path}"))
                    logger.warning("Supervisor: path missing", source_id=source_id, path=source.source_path)
                    continue

                watcher = self._watchers.get(source_id)
                if watcher is None:
                    logger.info("Supervisor: starting missing watcher", source_id=source_id)
                    await self.start_watcher(source_id)
                    asyncio.create_task(_emit_event(source_id, "recovery", message="Supervisor restarted missing watcher"))
                    continue

                # Check if watchdog observer died
                observer_dead = (
                    watcher._watchdog_observer is not None
                    and not watcher._watchdog_observer.is_alive()
                )
                poll_task_dead = (
                    watcher._poll_task is not None
                    and watcher._poll_task.done()
                )
                if observer_dead or poll_task_dead:
                    logger.warning("Supervisor: dead watcher detected, restarting", source_id=source_id)
                    await self.stop_watcher(source_id)
                    await self.start_watcher(source_id)
                    asyncio.create_task(_emit_event(source_id, "recovery", severity="warn", message="Supervisor recovered dead watcher"))
                    continue

                # Healthy — update heartbeat
                asyncio.create_task(_update_source_status(
                    source_id, "running",
                    watch_last_heartbeat_at=datetime.now(timezone.utc),
                    watch_last_error=None,
                ))

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Supervisor error for source", source_id=source_id, error=str(exc))

    # ------------------------------------------------------------------
    # Status & force-sync
    # ------------------------------------------------------------------

    def get_status(self, source_id: str) -> Optional[dict]:
        """Get watcher status for a source. Returns None if not running."""
        watcher = self._watchers.get(source_id)
        return watcher.status if watcher else None

    def get_all_statuses(self) -> list[dict]:
        """Get status for all active watchers."""
        return [w.status for w in self._watchers.values()]

    async def force_sync(self, source_id: str, db: AsyncSession, allow_mass_delete: bool = False) -> dict:
        """
        Compare disk state vs indexed state and queue differences.

        Returns summary: {"new": int, "modified": int, "deleted": int, "unchanged": int}

        Refuses to run against an unhealthy root, and refuses a reconcile that
        would wipe most of the index (see _is_mass_deletion) unless the caller
        passes allow_mass_delete=True to confirm an intentional bulk removal.
        """
        stmt = select(Source).where(Source.id == source_id)
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()

        if not source:
            raise ValueError(f"Source not found: {source_id}")
        if source.source_type != "directory":
            raise ValueError(f"Source {source_id} is not a directory type")

        root = Path(source.source_path)
        health, detail = await _probe_root_health(root)
        if health != "ok":
            raise ValueError(detail or f"Watch root unhealthy: {source.source_path}")

        extensions = source.watch_extensions or []
        max_depth = source.watch_depth
        max_size_mb = source.watch_max_file_size_mb
        collection_name = source.collection_name or ""
        path_excludes = source.path_excludes or []

        disk_files = await _scan_directory(root, extensions, max_depth, max_size_mb, path_excludes)
        indexed = await _get_indexed_file_hashes(db, source_id)

        new_files = set(disk_files) - set(indexed)
        deleted_files = set(indexed) - set(disk_files)
        common = set(disk_files) & set(indexed)

        if not allow_mass_delete and _is_mass_deletion(len(indexed), len(deleted_files)):
            raise ValueError(
                f"Refusing mass deletion: {len(deleted_files)}/{len(indexed)} indexed files "
                f"are missing from {root}. If this is an intended bulk removal, re-run with "
                f"allow_mass_delete=true."
            )

        modified_files: list[str] = []
        unchanged_count = 0

        for fp_str in common:
            file_hash = await _compute_file_hash(Path(fp_str))
            if file_hash and file_hash != indexed[fp_str]:
                modified_files.append(fp_str)
            else:
                unchanged_count += 1

        logger.info(
            "Force-sync analysis",
            source_id=source_id,
            new=len(new_files),
            deleted=len(deleted_files),
            modified=len(modified_files),
            unchanged=unchanged_count,
        )

        # Delete vectors + records for removed files. Target every collection
        # the source writes to (bound libraries, or its own when unbound) — not
        # just source.collection_name — so RAG's collection is actually cleaned.
        target_collections = await _resolve_target_collections(db, source_id, collection_name or None)
        for fp_str in deleted_files:
            try:
                rel_path = str(Path(fp_str).relative_to(root))
            except ValueError:
                rel_path = fp_str
            for coll in target_collections:
                await _delete_vectors_for_file(coll, rel_path)
            await _delete_scraped_record(db, source_id, fp_str)

        await db.commit()

        # Queue a per-file re-index for each changed file. Deletions were
        # already handled above (vectors + DocumentContent rows removed); new
        # and modified files get the same single-file path the live watcher
        # uses, so the cost scales with the change set, not the source size.
        for fp_str in list(new_files) + modified_files:
            asyncio.create_task(reindex_file(source_id, fp_str))

        return {
            "new": len(new_files),
            "modified": len(modified_files),
            "deleted": len(deleted_files),
            "unchanged": unchanged_count,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

watcher_manager = WatcherManager()
