"""
Source management.

Handles CRUD operations for knowledge sources.
"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
import structlog

from app.core.config import get_settings
from app.core.utils import generate_collection_name
from app.models import Source, IndexingLog, Project, Library, LibrarySource

from .qdrant_client import get_qdrant_client

settings = get_settings()
logger = structlog.get_logger()


class SourceManager:
    """
    Manages knowledge source CRUD operations.

    Handles:
    - Source listing and filtering
    - Source creation with collection name generation
    - Source updates (name, description)
    - URL management (add/remove)
    - Source deletion with Qdrant cleanup
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = get_qdrant_client()

    def _generate_collection_name(self, name: str, source_id: str) -> str:
        """Generate a user-friendly Qdrant collection name for a knowledge source.

        Format: {prefix}{slugified_name}_{short_id}
        Example: "kb_api_documentation_abc12345"
        """
        return generate_collection_name(
            name=name,
            unique_id=source_id,
            prefix="kb_"
        )

    async def _get_library_collections(self, source_id: str) -> list[str]:
        """Qdrant collections the source's chunks are written to via library bindings.

        Mirrors BaseIndexer._get_collections_for_source: when a source is bound to
        libraries the indexer writes to each library's collection (not the
        source's own), so deletions must target those too. Returns [] when the
        source is unbound (it owns its collection instead).
        """
        stmt = (
            select(Library.collection_name)
            .join(LibrarySource, LibrarySource.library_id == Library.id)
            .where(LibrarySource.source_id == source_id)
        )
        return [c for c in (await self.db.execute(stmt)).scalars().all() if c]

    async def _get_chunk_collections(self, source: Source) -> list[str]:
        """Every Qdrant collection holding this source's chunks.

        The source's own collection is the primary copy the search path reads;
        each bound library's collection holds a mirror. Point-level deletions
        must target all of them or chunks for removed files/URLs leak in the
        collection RAG actually reads.
        """
        colls = [source.collection_name] if source.collection_name else []
        colls += await self._get_library_collections(source.id)
        return colls

    async def list_sources(
        self,
        project_id: Optional[str] = None
    ) -> list[Source]:
        """List all knowledge sources, optionally filtered by project."""
        if project_id:
            stmt = select(Source).where(
                (Source.project_id == project_id) |
                (Source.project_id.is_(None))
            ).order_by(Source.created_at.desc())
        else:
            stmt = select(Source).order_by(Source.created_at.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_global_sources(self) -> list[Source]:
        """List all global knowledge sources (project_id is NULL)."""
        stmt = select(Source).where(
            Source.project_id.is_(None)
        ).order_by(Source.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_source(self, source_id: str) -> Optional[Source]:
        """Get a specific knowledge source."""
        stmt = select(Source).where(Source.id == source_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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
        """Create a new knowledge source.

        Enrichment authority note (3rd recurrence — do not lose this):
        enrichment_enabled, enrichment_taxonomy_id, and enrichment_model belong
        to the SOURCE, not the library. Libraries aggregate sources but do not
        own or inherit enrichment configuration. Always set these fields at
        creation time (or via update_source) — never derive them from a library
        binding. Callers that omit them will get enrichment_enabled=False and no
        taxonomy assigned, so chunks will not be enriched after indexing.
        """
        if project_id:
            proj_stmt = select(Project).where(Project.id == project_id)
            proj_result = await self.db.execute(proj_stmt)
            if not proj_result.scalar_one_or_none():
                raise ValueError("Project not found")

        # Sub-source validation. A sub-source is a filtered view over a root —
        # no own collection, no own watcher, parent must be a root.
        canonical_prefix = None
        canonical_excludes: Optional[list[str]] = None
        if parent_source_id is not None:
            from app.services.ingestion.path_utils import (
                canonicalise_path,
                normalise_excludes,
                path_under,
            )

            parent_stmt = select(Source).where(Source.id == parent_source_id)
            parent_result = await self.db.execute(parent_stmt)
            parent = parent_result.scalar_one_or_none()
            if parent is None:
                raise ValueError(f"Parent source not found: {parent_source_id}")
            if parent.parent_source_id is not None:
                raise ValueError(
                    "Cannot create a sub-source whose parent is itself a sub-source "
                    "(two-level hierarchy only)"
                )
            if parent.source_type != "directory":
                raise ValueError("Sub-sources are only supported under directory roots")

            if source_type not in (None, "directory"):
                raise ValueError(
                    f"Sub-sources must inherit source_type=directory, got '{source_type}'"
                )
            source_type = "directory"

            if not path_prefix:
                raise ValueError("Sub-sources require a path_prefix")
            canonical_prefix = canonicalise_path(path_prefix)
            if not path_under(canonical_prefix, parent.source_path):
                raise ValueError(
                    f"path_prefix '{canonical_prefix}' is not under parent root "
                    f"'{parent.source_path}'"
                )

            canonical_excludes = normalise_excludes(path_excludes)
            # Sub-source's source_path mirrors its prefix so downstream UI
            # surfacing remains consistent (existing API contracts read
            # source_path everywhere).
            source_path = canonical_prefix
        else:
            # Root path_excludes (if any) — canonicalise at create time.
            if path_excludes:
                from app.services.ingestion.path_utils import normalise_excludes
                canonical_excludes = normalise_excludes(path_excludes)

        selected_urls_json = None
        if source_type == "url" and selected_urls:
            selected_urls_json = json.dumps(selected_urls)

        selected_files_json = None
        if source_type == "file" and selected_files:
            selected_files_json = json.dumps(selected_files)

        # YouTube source defaults (#133): one source = one channel. Default to a
        # shallow recent backfill that auto-refreshes daily so new uploads are
        # picked up without the caller having to wire freshness explicitly.
        if source_type == "youtube":
            if youtube_backfill_mode not in (None, "all", "recent"):
                raise ValueError("youtube_backfill_mode must be 'all' or 'recent'")
            youtube_backfill_mode = youtube_backfill_mode or "recent"
            if youtube_recent_count is None:
                youtube_recent_count = 50
            # Default freshness so new uploads are pulled automatically. Applied
            # independently so an explicit policy without a cadence still schedules.
            if freshness_policy is None:
                freshness_policy = "automatic"
            if refresh_interval_days is None:
                refresh_interval_days = 1
            if stale_after_days is None:
                stale_after_days = 7

        source = Source(
            name=name,
            source_type=source_type,
            source_path=source_path,
            project_id=project_id,
            status="pending" if parent_source_id is None else "indexed",
            selected_urls=selected_urls_json,
            selected_files=selected_files_json,
            description=description,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            custom_metadata=custom_metadata or {},
            freshness_policy=freshness_policy or "none",
            stale_after_days=stale_after_days,
            refresh_interval_days=refresh_interval_days,
            enrichment_enabled=enrichment_enabled,
            enrichment_taxonomy_id=enrichment_taxonomy_id,
            enrichment_model=enrichment_model,
            parent_source_id=parent_source_id,
            path_prefix=canonical_prefix,
            path_excludes=canonical_excludes,
            youtube_backfill_mode=youtube_backfill_mode,
            youtube_recent_count=youtube_recent_count,
        )
        self.db.add(source)
        await self.db.flush()
        await self.db.refresh(source)

        # Sub-sources never own a Qdrant collection — they query their parent's.
        if parent_source_id is None:
            source.collection_name = self._generate_collection_name(name, source.id)
            await self.db.flush()

        return source

    async def update_source(
        self,
        source_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> Source:
        """Update a knowledge source's metadata and configuration."""
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if name is not None:
            source.name = name
        if description is not None:
            source.description = description

        # Watcher fields
        watcher_fields = [
            "watch_enabled", "watch_mode", "watch_poll_interval_seconds",
            "watch_debounce_seconds", "watch_max_file_size_mb",
            "watch_extensions", "watch_depth",
        ]
        for field in watcher_fields:
            if kwargs.get(field) is not None:
                setattr(source, field, kwargs[field])

        # Enrichment fields
        enrichment_fields = [
            "enrichment_enabled", "enrichment_taxonomy_id", "enrichment_model",
        ]
        for field in enrichment_fields:
            if kwargs.get(field) is not None:
                setattr(source, field, kwargs[field])

        # YouTube source fields (depth is editable post-creation)
        if kwargs.get("youtube_backfill_mode") not in (None, "all", "recent"):
            raise ValueError("youtube_backfill_mode must be 'all' or 'recent'")
        youtube_fields = ["youtube_backfill_mode", "youtube_recent_count"]
        for field in youtube_fields:
            if kwargs.get(field) is not None:
                setattr(source, field, kwargs[field])

        # Sub-source / path-overlay fields. Re-canonicalise before storing so
        # the filter overlay (which uses ``folder_ancestors`` MatchAny) finds
        # them. ``parent_source_id`` is intentionally not updatable here —
        # re-parenting requires a fresh sub-source.
        from app.services.ingestion.path_utils import (
            canonicalise_path,
            normalise_excludes,
            path_under,
        )
        if kwargs.get("path_prefix") is not None:
            new_prefix = kwargs["path_prefix"]
            if new_prefix:
                new_prefix = canonicalise_path(new_prefix)
                if source.parent_source_id:
                    parent_stmt = select(Source).where(Source.id == source.parent_source_id)
                    parent_result = await self.db.execute(parent_stmt)
                    parent = parent_result.scalar_one_or_none()
                    if parent and not path_under(new_prefix, parent.source_path):
                        raise ValueError(
                            f"path_prefix '{new_prefix}' is not under parent root "
                            f"'{parent.source_path}'"
                        )
            source.path_prefix = new_prefix
            if source.parent_source_id and new_prefix:
                source.source_path = new_prefix
        if kwargs.get("path_excludes") is not None:
            source.path_excludes = normalise_excludes(kwargs["path_excludes"])

        # Freshness lifecycle fields
        freshness_fields = [
            "freshness_policy", "stale_after_days", "refresh_interval_days",
        ]
        for field in freshness_fields:
            if kwargs.get(field) is not None:
                setattr(source, field, kwargs[field])

        # Recompute next_refresh_at when freshness config changes
        if any(kwargs.get(f) is not None for f in freshness_fields):
            from app.services.freshness_service import compute_next_refresh_at
            source.next_refresh_at = compute_next_refresh_at(source)

        source.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(source)

        logger.info("Updated knowledge source", source_id=source_id, name=name, description=description)
        return source

    async def add_urls_to_source(
        self,
        source_id: str,
        urls: list[str],
    ) -> Source:
        """Add new URLs to an existing URL source."""
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if source.source_type != "url":
            raise ValueError("Can only add URLs to URL-type sources")

        # Get existing URLs
        existing_urls = []
        if source.selected_urls:
            try:
                existing_urls = json.loads(source.selected_urls)
            except json.JSONDecodeError:
                existing_urls = []

        # Add new URLs (avoid duplicates)
        existing_set = set(existing_urls)
        new_urls = [url for url in urls if url not in existing_set]

        if not new_urls:
            return source  # No new URLs to add

        all_urls = existing_urls + new_urls
        source.selected_urls = json.dumps(all_urls)
        source.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(source)

        logger.info("Added URLs to source", source_id=source_id, added_count=len(new_urls))
        return source

    async def remove_urls_from_source(
        self,
        source_id: str,
        urls: list[str],
    ) -> Source:
        """Remove URLs from an existing URL source and delete their vectors."""
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if source.source_type != "url":
            raise ValueError("Can only remove URLs from URL-type sources")

        # Get existing URLs
        existing_urls = []
        if source.selected_urls:
            try:
                existing_urls = json.loads(source.selected_urls)
            except json.JSONDecodeError:
                existing_urls = []

        # Remove specified URLs
        urls_to_remove = set(urls)
        remaining_urls = [url for url in existing_urls if url not in urls_to_remove]

        # Delete vectors from Qdrant for removed URLs. The "source" payload is
        # the page URL; purge from every collection holding this source's chunks
        # (its own primary copy plus any bound-library mirrors).
        if urls_to_remove:
            target_collections = await self._get_chunk_collections(source)
            for coll in target_collections:
                try:
                    self.client.delete(
                        collection_name=coll,
                        points_selector=Filter(
                            must=[
                                FieldCondition(
                                    key="source",
                                    match=MatchAny(any=list(urls_to_remove))
                                )
                            ]
                        )
                    )
                    logger.info("Deleted vectors for removed URLs", source_id=source_id, collection=coll, urls=list(urls_to_remove))
                except Exception as e:
                    logger.warning("Failed to delete vectors for removed URLs", collection=coll, error=str(e))

        # Delete indexing logs for removed URLs
        delete_logs_stmt = delete(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.url.in_(list(urls_to_remove))
        )
        await self.db.execute(delete_logs_stmt)

        source.selected_urls = json.dumps(remaining_urls)
        source.updated_at = datetime.utcnow()

        # Update document/chunk counts (approximate - we'd need to recalculate from Qdrant)
        removed_count = len(urls_to_remove.intersection(set(existing_urls)))
        if removed_count > 0 and source.document_count > 0:
            source.document_count = max(0, source.document_count - removed_count)

        await self.db.flush()
        await self.db.refresh(source)

        logger.info("Removed URLs from source", source_id=source_id, removed_count=removed_count)
        return source

    async def add_files_to_source(
        self,
        source_id: str,
        files: list[dict],
    ) -> Source:
        """Add new files to an existing file source.

        Args:
            source_id: The knowledge source ID
            files: List of file info dicts with keys: path, original_name, size_bytes
        """
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if source.source_type != "file":
            raise ValueError("Can only add files to file-type sources")

        # Get existing files
        existing_files = []
        if source.selected_files:
            try:
                existing_files = json.loads(source.selected_files)
            except json.JSONDecodeError:
                existing_files = []

        # Add new files (avoid duplicates by path)
        existing_paths = {f["path"] for f in existing_files}
        new_files = [f for f in files if f["path"] not in existing_paths]

        if not new_files:
            return source  # No new files to add

        all_files = existing_files + new_files
        source.selected_files = json.dumps(all_files)
        source.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(source)

        logger.info("Added files to source", source_id=source_id, added_count=len(new_files))
        return source

    async def remove_files_from_source(
        self,
        source_id: str,
        file_paths: list[str],
    ) -> Source:
        """Remove files from an existing file source and delete their vectors.

        Args:
            source_id: The knowledge source ID
            file_paths: List of file paths to remove
        """
        import os
        from pathlib import Path

        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        if source.source_type != "file":
            raise ValueError("Can only remove files from file-type sources")

        # Get existing files
        existing_files = []
        if source.selected_files:
            try:
                existing_files = json.loads(source.selected_files)
            except json.JSONDecodeError:
                existing_files = []

        # Identify files to remove
        paths_to_remove = set(file_paths)
        remaining_files = [f for f in existing_files if f["path"] not in paths_to_remove]
        removed_files = [f for f in existing_files if f["path"] in paths_to_remove]

        # Delete vectors from Qdrant for removed files. FileIndexer keys the
        # "source" payload by basename, so match on that — and purge from every
        # collection holding this source's chunks (its own primary copy plus any
        # bound-library mirrors).
        if removed_files:
            target_collections = await self._get_chunk_collections(source)
            source_names = [Path(f["path"]).name for f in removed_files]
            for coll in target_collections:
                try:
                    self.client.delete(
                        collection_name=coll,
                        points_selector=Filter(
                            must=[
                                FieldCondition(
                                    key="source",
                                    match=MatchAny(any=source_names)
                                )
                            ]
                        )
                    )
                    logger.info("Deleted vectors for removed files", source_id=source_id, collection=coll, files=source_names)
                except Exception as e:
                    logger.warning("Failed to delete vectors for removed files", collection=coll, error=str(e))

        # Delete indexing logs for removed files
        delete_logs_stmt = delete(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.url.in_(list(paths_to_remove))
        )
        await self.db.execute(delete_logs_stmt)

        # Delete physical files from disk
        for file_info in removed_files:
            file_path = file_info["path"]
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info("Deleted file from disk", path=file_path)
            except Exception as e:
                logger.warning("Failed to delete file from disk", path=file_path, error=str(e))

        source.selected_files = json.dumps(remaining_files)
        source.updated_at = datetime.utcnow()

        # Update document count
        removed_count = len(removed_files)
        if removed_count > 0 and source.document_count > 0:
            source.document_count = max(0, source.document_count - removed_count)

        await self.db.flush()
        await self.db.refresh(source)

        logger.info("Removed files from source", source_id=source_id, removed_count=removed_count)
        return source

    async def delete_source(self, source_id: str) -> bool:
        """Delete a knowledge source and clean up its vectors.

        Sub-sources are filtered views that own no chunks — dropping the row is
        enough. ON DELETE CASCADE on the self-referential FK ensures deleting a
        root also drops its sub-sources.

        For a real source, chunks may live in shared library collections (when
        the source is bound to libraries) rather than its own collection. We
        therefore:
          - purge THIS source's chunks (by source_id) from each bound-library
            collection, without dropping the shared collection, and
          - drop the source's own per-source collection if it has one.
        """
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        is_sub_source = bool(getattr(source, "parent_source_id", None))

        if not is_sub_source:
            # Remove this source's chunks from any shared library collections.
            for coll in await self._get_library_collections(source_id):
                try:
                    self.client.delete(
                        collection_name=coll,
                        points_selector=Filter(
                            must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
                        ),
                    )
                    logger.info("Purged source chunks from library collection",
                                collection=coll, source_id=source_id)
                except Exception as e:
                    logger.warning("Failed to purge source chunks from library collection",
                                   collection=coll, source_id=source_id, error=str(e))

            # Drop the source's own (per-source) collection if present.
            if source.collection_name:
                try:
                    self.client.delete_collection(source.collection_name)
                    logger.info("Deleted Qdrant collection", collection=source.collection_name)
                except Exception as e:
                    logger.warning("Failed to delete Qdrant collection",
                                 collection=source.collection_name, error=str(e))

        await self.db.delete(source)
        await self.db.flush()
        return True
