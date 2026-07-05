"""
Ingestion service orchestrator.

Main entry point that coordinates all ingestion operations by delegating
to specialized managers and indexers.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Source, IndexingLog, Job

from .types import ScanResult, IndexingStatus, IndexingLogSummary
from .source_manager import SourceManager
from .log_manager import LogManager
from .url_scanner import UrlScanner
from .indexers import DirectoryIndexer, FileIndexer, UrlIndexer, YouTubeIndexer

logger = structlog.get_logger()


class IngestionService:
    """
    Main ingestion service that orchestrates all operations.

    Delegates to specialized components:
    - SourceManager: Source CRUD operations
    - LogManager: Indexing logs and status
    - UrlScanner: URL structure scanning
    - Indexers: Type-specific indexing (directory, file, URL)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.source_manager = SourceManager(db)
        self.log_manager = LogManager(db)
        self.url_scanner = UrlScanner()
        self.directory_indexer = DirectoryIndexer(db)
        self.file_indexer = FileIndexer(db)
        self.url_indexer = UrlIndexer(db)
        self.youtube_indexer = YouTubeIndexer(db)

    # ==================== Source Management (delegated) ====================

    async def list_sources(self, project_id: Optional[str] = None) -> list[Source]:
        """List all knowledge sources, optionally filtered by project."""
        return await self.source_manager.list_sources(project_id)

    async def list_global_sources(self) -> list[Source]:
        """List all global knowledge sources (project_id is NULL)."""
        return await self.source_manager.list_global_sources()

    async def get_source(self, source_id: str) -> Optional[Source]:
        """Get a specific knowledge source."""
        return await self.source_manager.get_source(source_id)

    async def create_source(
        self,
        name: str,
        source_type: str,
        source_path: str,
        project_id: Optional[str] = None,
        selected_urls: Optional[list[str]] = None,
        selected_files: Optional[list[dict]] = None,
        description: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None,
        custom_metadata: Optional[dict] = None,
        freshness_policy: Optional[str] = None,
        stale_after_days: Optional[int] = None,
        refresh_interval_days: Optional[int] = None,
        enrichment_enabled: bool = False,
        enrichment_taxonomy_id: Optional[str] = None,
        enrichment_model: Optional[str] = None,
        parent_source_id: Optional[str] = None,
        path_prefix: Optional[str] = None,
        path_excludes: Optional[list[str]] = None,
        youtube_backfill_mode: Optional[str] = None,
        youtube_recent_count: Optional[int] = None,
    ) -> Source:
        """Create a new knowledge source."""
        return await self.source_manager.create_source(
            name=name,
            source_type=source_type,
            source_path=source_path,
            project_id=project_id,
            selected_urls=selected_urls,
            selected_files=selected_files,
            description=description,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            custom_metadata=custom_metadata or {},
            freshness_policy=freshness_policy,
            stale_after_days=stale_after_days,
            refresh_interval_days=refresh_interval_days,
            enrichment_enabled=enrichment_enabled,
            enrichment_taxonomy_id=enrichment_taxonomy_id,
            enrichment_model=enrichment_model,
            parent_source_id=parent_source_id,
            path_prefix=path_prefix,
            path_excludes=path_excludes,
            youtube_backfill_mode=youtube_backfill_mode,
            youtube_recent_count=youtube_recent_count,
        )

    async def update_source(
        self,
        source_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> Source:
        """Update a knowledge source's metadata and configuration."""
        return await self.source_manager.update_source(source_id, name, description, **kwargs)

    async def add_urls_to_source(self, source_id: str, urls: list[str]) -> Source:
        """Add new URLs to an existing URL source."""
        return await self.source_manager.add_urls_to_source(source_id, urls)

    async def remove_urls_from_source(self, source_id: str, urls: list[str]) -> Source:
        """Remove URLs from an existing URL source and delete their vectors."""
        return await self.source_manager.remove_urls_from_source(source_id, urls)

    async def add_files_to_source(self, source_id: str, files: list[dict]) -> Source:
        """Add new files to an existing file source."""
        return await self.source_manager.add_files_to_source(source_id, files)

    async def remove_files_from_source(self, source_id: str, file_paths: list[str]) -> Source:
        """Remove files from an existing file source and delete their vectors."""
        return await self.source_manager.remove_files_from_source(source_id, file_paths)

    async def delete_source(self, source_id: str) -> bool:
        """Delete a knowledge source and its Qdrant collection."""
        return await self.source_manager.delete_source(source_id)

    # ==================== Indexing Status (delegated) ====================

    async def get_indexing_status(self, source_id: str) -> IndexingStatus:
        """Get the current indexing status of a knowledge source."""
        return await self.log_manager.get_indexing_status(source_id)

    # ==================== Indexing Logs (delegated) ====================

    async def get_indexing_logs(
        self,
        source_id: str,
        status_filter: Optional[str] = None,
        limit: int = 500
    ) -> IndexingLogSummary:
        """Get indexing logs for a knowledge source with summary stats."""
        return await self.log_manager.get_indexing_logs(source_id, status_filter, limit)

    async def clear_indexing_logs(self, source_id: str) -> bool:
        """Clear all indexing logs for a knowledge source."""
        return await self.log_manager.clear_indexing_logs(source_id)

    # ==================== URL Scanning (delegated) ====================

    async def scan_url(
        self,
        url: str,
        max_depth: int = 2,
        path_scope: Optional[str] = None,
        sitemap_url: Optional[str] = None,
        path_filter: Optional[str] = None,
        auto_discover_sitemap: bool = False
    ) -> ScanResult:
        """Scan a URL and return the site tree structure."""
        return await self.url_scanner.scan_url(
            url=url,
            max_depth=max_depth,
            path_scope=path_scope,
            sitemap_url=sitemap_url,
            path_filter=path_filter,
            auto_discover_sitemap=auto_discover_sitemap,
        )

    # ==================== Indexing Operations ====================

    async def start_indexing(self, source_id: str, force: bool = False) -> str:
        """
        Start indexing a knowledge source.

        Args:
            source_id: Source to index.
            force: When True, override the "already_indexing" guard by marking
                any in-flight or queued index_source jobs for this source as
                failed and resetting source status. Use when a previous run
                has stalled (e.g., hung Playwright browser, lost worker) and
                left the source stuck in ``status='indexing'``.

        Returns status message ("started" or "already_indexing").
        """
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if source.status == "indexing":
            if not force:
                return "already_indexing"
            # Force path: clear stale jobs and reset source status before re-starting.
            await self.db.execute(
                update(Job)
                .where(
                    Job.job_type.in_(
                        ["index_source", "incremental_index", "retry_failed", "selective_index"]
                    ),
                    Job.status.in_(["queued", "running"]),
                    Job.payload["source_id"].as_string() == source_id,
                )
                .values(
                    status="failed",
                    error_message="Superseded by force re-trigger",
                    completed_at=datetime.utcnow(),
                )
            )
            logger.info(
                "Force re-trigger: cleared stale jobs and resetting source",
                source_id=source_id,
            )

        source.status = "indexing"
        source.error_message = None
        source.progress = 0
        source.progress_total = 0
        source.progress_message = "Starting indexing..."
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

        return "started"

    async def _recalc_source_libraries(self, source_id: str) -> None:
        """Recompute cached stats for every library this source belongs to.

        Called after an index run so a library bound to an already-indexed
        source reflects the Document rows created during the (bind-triggered)
        reindex, rather than the stale pre-index count. Best-effort — stats are
        a display concern and must never fail the index.
        """
        try:
            from app.models import LibrarySource
            from app.services.library import LibraryService

            lib_ids = (
                await self.db.execute(
                    select(LibrarySource.library_id).where(
                        LibrarySource.source_id == source_id
                    )
                )
            ).scalars().all()
            lib_svc = LibraryService(self.db)
            for lib_id in lib_ids:
                await lib_svc.recalculate_stats(lib_id)
        except Exception as e:
            logger.warning(
                "Post-index library stats recalc failed",
                source_id=source_id, error=str(e),
            )

    async def execute_indexing(self, source_id: str) -> None:
        """
        Execute the indexing operation. Call from background task.
        """
        source = await self.get_source(source_id)
        if not source:
            logger.error("Source not found for background indexing", source_id=source_id)
            return

        try:
            # Map source type to indexer
            indexer_map = {
                "directory": self.directory_indexer,
                "url": self.url_indexer,
                "file": self.file_indexer,
                "youtube": self.youtube_indexer,
            }
            indexer = indexer_map.get(source.source_type)
            if indexer:
                # Load structured metadata for Qdrant payload injection
                indexer._load_source_metadata(source)
                await indexer.index(source)
                # Refresh cached stats for any libraries this source belongs to.
                # A bind-triggered reindex creates the library's Document rows
                # during index(); without this the library's document/chunk
                # counts stay at their pre-index value (often 0).
                await self._recalc_source_libraries(source_id)
            elif source.source_type == "collection":
                # Adopted Qdrant collections are managed externally; nothing to index
                logger.info("Skipping indexing for adopted collection", source_id=source_id)
                source.status = "indexed"
                source.progress_message = "Adopted collection — data managed externally"
                source.progress_updated_at = datetime.utcnow()
                await self.db.flush()
                return
            else:
                raise ValueError(f"Unsupported source type: {source.source_type}")

        except Exception as e:
            logger.error("Indexing failed", source_id=source_id, error=str(e))
            await self.db.rollback()
            source.status = "error"
            source.error_message = str(e)
            source.progress_message = f"Failed: {str(e)}"
            source.progress_updated_at = datetime.utcnow()
            await self.db.flush()
            raise

    async def execute_incremental_file_indexing(
        self, source_id: str, new_files: list[dict]
    ) -> None:
        """Index only newly added files. Call from background task."""
        source = await self.get_source(source_id)
        if not source:
            logger.error("Source not found for incremental indexing", source_id=source_id)
            return

        if source.source_type != "file":
            raise ValueError("Incremental file indexing only supports file sources")

        try:
            self.file_indexer._load_source_metadata(source)
            await self.file_indexer.index_new_files(source, new_files)
        except Exception as e:
            logger.error("Incremental indexing failed", source_id=source_id, error=str(e))
            source.status = "error"
            source.error_message = str(e)
            source.progress_message = f"Failed: {str(e)}"
            source.progress_updated_at = datetime.utcnow()
            await self.db.flush()
            raise

    # ==================== Retry Operations ====================

    async def retry_failed_urls(self, source_id: str) -> tuple[str, int]:
        """
        Retry indexing only failed URLs for a knowledge source.
        Returns (status, retry_count).
        """
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if source.status == "indexing":
            return ("already_indexing", 0)

        failed_stmt = select(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.status == "failed"
        )
        failed_result = await self.db.execute(failed_stmt)
        failed_logs = failed_result.scalars().all()

        if not failed_logs:
            return ("no_failures", 0)

        # Reset failed logs to pending
        for log in failed_logs:
            log.status = "pending"
            log.error_message = None
            log.scrape_duration_ms = None
            log.embed_duration_ms = None
        await self.db.flush()

        source.status = "indexing"
        source.error_message = None
        source.progress = 0
        source.progress_total = len(failed_logs)
        source.progress_message = f"Retrying {len(failed_logs)} failed URLs..."
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

        return ("started", len(failed_logs))
