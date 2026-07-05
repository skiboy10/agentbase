"""
MCP Tools for Source Management — Core

CRUD, indexing, search, and filter tools for sources.
Upload/ingest tools are in sources_upload.py.
Document operations are in sources_docs.py.
"""

import asyncio
from typing import Annotated, Literal, Optional

import structlog
from pydantic import Field

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.core.auth import Scope, check_mcp_scope
from app.core.events import publish_source_event
from app.services import IngestionService, RAGService, run_indexing_task

# The event loop holds only weak refs to tasks; keep background indexing
# tasks referenced until done or they can be garbage-collected mid-run.
_background_tasks: set[asyncio.Task] = set()

logger = structlog.get_logger()


def _sanitize_for_json(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    try:
        import numpy as np
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]
    return obj


def _source_to_summary_dict(source) -> dict:
    """Convert KnowledgeSource model to summary dict (no selected_urls/selected_files)."""
    import json as json_lib

    from app.services.freshness_service import get_freshness_status

    # Count URLs/files without including the full lists
    url_count = 0
    if source.selected_urls:
        try:
            url_count = len(json_lib.loads(source.selected_urls))
        except (json_lib.JSONDecodeError, TypeError):
            pass

    file_count = 0
    if source.selected_files:
        try:
            file_count = len(json_lib.loads(source.selected_files))
        except (json_lib.JSONDecodeError, TypeError):
            pass

    return {
        "id": source.id,
        "name": source.name,
        "description": source.description,
        "source_type": source.source_type,
        "source_path": source.source_path,
        "project_id": source.project_id,
        "status": source.status,
        "last_indexed": source.last_indexed.isoformat() if source.last_indexed else None,
        "document_count": source.document_count,
        "chunk_count": source.chunk_count,
        "error_message": source.error_message,
        "progress": source.progress,
        "progress_total": source.progress_total,
        "progress_message": source.progress_message,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "selected_url_count": url_count,
        "selected_file_count": file_count,
        "collection_name": source.collection_name,
        "embedding_provider": source.embedding_provider,
        "embedding_model": source.embedding_model,
        "custom_metadata": source.custom_metadata or {},
        "enrichment_enabled": source.enrichment_enabled,
        "enrichment_taxonomy_id": source.enrichment_taxonomy_id,
        "enrichment_model": source.enrichment_model,
        "freshness_policy": source.freshness_policy,
        "stale_after_days": source.stale_after_days,
        "refresh_interval_days": source.refresh_interval_days,
        "next_refresh_at": source.next_refresh_at.isoformat() if source.next_refresh_at else None,
        "freshness_status": get_freshness_status(source),
        "parent_source_id": getattr(source, "parent_source_id", None),
        "path_prefix": getattr(source, "path_prefix", None),
        "path_excludes": getattr(source, "path_excludes", None),
    }


def _source_to_dict(source) -> dict:
    """Convert KnowledgeSource model to full dict (includes selected_urls/selected_files)."""
    import json as json_lib

    selected_urls = None
    if source.selected_urls:
        try:
            selected_urls = json_lib.loads(source.selected_urls)
        except (json_lib.JSONDecodeError, TypeError):
            pass

    selected_files = None
    if source.selected_files:
        try:
            selected_files = json_lib.loads(source.selected_files)
        except (json_lib.JSONDecodeError, TypeError):
            pass

    from app.services.freshness_service import get_freshness_status

    return {
        "id": source.id,
        "name": source.name,
        "description": source.description,
        "source_type": source.source_type,
        "source_path": source.source_path,
        "project_id": source.project_id,
        "status": source.status,
        "last_indexed": source.last_indexed.isoformat() if source.last_indexed else None,
        "document_count": source.document_count,
        "chunk_count": source.chunk_count,
        "error_message": source.error_message,
        "progress": source.progress,
        "progress_total": source.progress_total,
        "progress_message": source.progress_message,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "selected_urls": selected_urls,
        "selected_files": selected_files,
        "collection_name": source.collection_name,
        "embedding_provider": source.embedding_provider,
        "embedding_model": source.embedding_model,
        "custom_metadata": source.custom_metadata or {},
        "enrichment_enabled": source.enrichment_enabled,
        "enrichment_taxonomy_id": source.enrichment_taxonomy_id,
        "enrichment_model": source.enrichment_model,
        "freshness_policy": source.freshness_policy,
        "stale_after_days": source.stale_after_days,
        "refresh_interval_days": source.refresh_interval_days,
        "next_refresh_at": source.next_refresh_at.isoformat() if source.next_refresh_at else None,
        "freshness_status": get_freshness_status(source),
        "parent_source_id": getattr(source, "parent_source_id", None),
        "path_prefix": getattr(source, "path_prefix", None),
        "path_excludes": getattr(source, "path_excludes", None),
    }


# ============================================================
# Source CRUD
# ============================================================

@mcp.tool(
    description=(
        "List all sources with pagination. Optional filters: project_id, freshness_status "
        "(current/aging/stale — only meaningful for sources with freshness_policy != none)."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_list_sources(
    project_id: Optional[str] = None,
    freshness_status: Optional[str] = None,
    parent_source_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List sources with optional filters and pagination.

    Returns:
        dict with keys:
            total (int) - total matching sources before pagination
            count (int) - number of items in this page
            offset (int) - current offset
            has_more (bool) - whether more pages exist
            next_offset (int|None) - offset for next page, None if no more
            items (list[dict]) - source dicts, each with keys:
                id (str), name (str), description (str|None),
                source_type (str), source_path (str), project_id (str|None),
                status (str), last_indexed (str|None - ISO datetime),
                document_count (int), chunk_count (int),
                error_message (str|None), progress (int|None),
                progress_total (int|None), progress_message (str|None),
                created_at (str - ISO datetime),
                selected_urls (list[str]|None),
                selected_files (list[str]|None),
                collection_name (str|None),
                embedding_provider (str|None), embedding_model (str|None),
                custom_metadata (dict),
                freshness_policy (str|None), stale_after_days (int|None),
                refresh_interval_days (int|None),
                next_refresh_at (str|None), freshness_status (str|None)
    """
    async with async_session_maker() as db:
        service = IngestionService(db)
        sources = await service.list_sources(project_id)
        by_id = {s.id: s for s in sources}
        results = [_source_to_summary_dict(source) for source in sources]
        if freshness_status:
            results = [r for r in results if r["freshness_status"] == freshness_status]

        # Sub-source filter:
        #   "root"  → roots only (parent_source_id IS NULL)
        #   <uuid>  → sub-sources of that specific root
        #   None    → all sources (roots + sub-sources)
        if parent_source_id is not None:
            if parent_source_id == "root":
                results = [r for r in results if not r.get("parent_source_id")]
            else:
                results = [
                    r for r in results if r.get("parent_source_id") == parent_source_id
                ]

        total_count = len(results)
        items = results[offset : offset + limit]

        # Derive sub-source doc counts for the returned page only (stored
        # column is 0 for sub-sources — see get_sub_source_document_counts).
        from app.api.sources.helpers import get_sub_source_document_counts
        page_sources = [by_id[r["id"]] for r in items if r["id"] in by_id]
        sub_doc_counts = await get_sub_source_document_counts(db, page_sources)
        for r in items:
            if r["id"] in sub_doc_counts:
                r["document_count"] = sub_doc_counts[r["id"]]

        return {
            "total": total_count,
            "count": len(items),
            "offset": offset,
            "has_more": offset + len(items) < total_count,
            "next_offset": offset + len(items) if offset + len(items) < total_count else None,
            "items": items,
        }


@mcp.tool(
    description="Get a source by ID with status, stats, and configuration.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_source(source_id: str) -> dict:
    """Get source details including status, stats, configuration, and URL/file lists.

    Returns:
        dict with keys:
            id (str), name (str), description (str|None), source_type (str),
            source_path (str), project_id (str|None), status (str),
            last_indexed (str|None - ISO datetime), document_count (int),
            chunk_count (int), error_message (str|None),
            progress (int|None), progress_total (int|None),
            progress_message (str|None), created_at (str - ISO datetime),
            selected_urls (list[str]|None), selected_files (list[str]|None),
            collection_name (str|None), embedding_provider (str|None),
            embedding_model (str|None), custom_metadata (dict),
            freshness_policy (str|None), stale_after_days (int|None),
            refresh_interval_days (int|None), next_refresh_at (str|None),
            freshness_status (str|None)
        On error: {"error": str}
    """
    async with async_session_maker() as db:
        service = IngestionService(db)
        source = await service.get_source(source_id)
        if not source:
            return {"error": f"Source not found: {source_id}"}
        result = _source_to_dict(source)
        # Sub-sources are never indexed on their own; derive their document
        # count from the parent's docs under path_prefix.
        from app.api.sources.helpers import get_sub_source_document_counts
        sub_doc_counts = await get_sub_source_document_counts(db, [source])
        if source.id in sub_doc_counts:
            result["document_count"] = sub_doc_counts[source.id]
        return result


@mcp.tool(
    description=(
        "Create a source (url/file/directory/youtube), then call agentbase_index_source. "
        "youtube: source_path=channel URL, youtube_backfill_mode=all|recent, "
        "youtube_recent_count=N; auto-refreshes daily. "
        "freshness_policy=none|automatic|manual. enrichment_enabled + "
        "enrichment_taxonomy_id/model to tag content."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_create_source(
    name: Annotated[str, Field(
        min_length=1, max_length=255,
        description="Display name, e.g. 'ACME Product Documentation'",
    )],
    source_type: Annotated[Literal["url", "file", "directory", "youtube"], Field(
        description="Kind of source to create",
    )],
    source_path: Annotated[str, Field(
        min_length=1, max_length=2048,
        description="Base URL, file path, directory path, or YouTube channel URL",
    )],
    project_id: Optional[str] = None,
    description: Optional[str] = None,
    selected_urls: Optional[list[str]] = None,
    embedding_provider: Annotated[Optional[str], Field(max_length=50)] = None,
    embedding_model: Annotated[Optional[str], Field(max_length=100)] = None,
    custom_metadata: Optional[dict] = None,
    freshness_policy: Annotated[Optional[Literal["none", "automatic", "manual"]], Field(
        description="Freshness lifecycle policy",
    )] = None,
    stale_after_days: Annotated[Optional[int], Field(ge=1, le=3650)] = None,
    refresh_interval_days: Annotated[Optional[int], Field(ge=1, le=3650)] = None,
    enrichment_enabled: bool = False,
    enrichment_taxonomy_id: Optional[str] = None,
    enrichment_model: Annotated[Optional[str], Field(max_length=100)] = None,
    parent_source_id: Optional[str] = None,
    path_prefix: Optional[str] = None,
    path_excludes: Optional[list[str]] = None,
    youtube_backfill_mode: Annotated[Optional[Literal["all", "recent"]], Field(
        description="How much of a YouTube channel's back catalogue to ingest",
    )] = None,
    youtube_recent_count: Annotated[Optional[int], Field(ge=1, le=1000)] = None,
) -> dict:
    """Create a new source.

    Sub-sources: pass ``parent_source_id`` + ``path_prefix`` to create a
    filtered view over an existing directory root. Sub-sources don't run
    their own watcher or own Qdrant chunks — they query the parent's
    collection with a ``folder_ancestors`` filter narrowed to the prefix.

    YouTube: set ``source_type="youtube"`` and ``source_path`` to a channel
    URL. ``youtube_backfill_mode`` ("all"|"recent") and ``youtube_recent_count``
    control how much of the back catalogue to ingest, per channel.
    """
    check_mcp_scope(Scope.WRITE)
    if source_type == "youtube":
        from app.core.url_validator import validate_youtube_channel_url
        try:
            validate_youtube_channel_url(source_path)
        except ValueError as e:
            return {"error": str(e)}
    async with async_session_maker() as db:
        service = IngestionService(db)
        try:
            source = await service.create_source(
                name=name,
                source_type=source_type,
                source_path=source_path,
                project_id=project_id,
                selected_urls=selected_urls,
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
            await db.commit()  # Commit the transaction so source persists
            logger.info("MCP: Created knowledge source", source_id=source.id, name=name)
            result = _source_to_dict(source)
            # Sub-sources derive their doc count from the parent's docs.
            from app.api.sources.helpers import get_sub_source_document_counts
            sub_doc_counts = await get_sub_source_document_counts(db, [source])
            if source.id in sub_doc_counts:
                result["document_count"] = sub_doc_counts[source.id]
            # Publish event for UI update
            await publish_source_event("created", source.id, {"name": name}, source="mcp")
            return result
        except ValueError as e:
            return {"error": str(e)}


@mcp.tool(
    description="Delete a source and its indexed documents. Irreversible.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_delete_source(source_id: str) -> dict:
    """Delete a source."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = IngestionService(db)
        source = await service.get_source(source_id)
        if not source:
            return {"error": f"Source not found: {source_id}"}

        try:
            await service.delete_source(source_id)
            await db.commit()  # Commit the deletion
            logger.info("MCP: Deleted source", source_id=source_id)
            # Publish event for UI update
            await publish_source_event("deleted", source_id, source="mcp")
            return {"status": "deleted", "id": source_id}
        except ValueError as e:
            return {"error": str(e)}


@mcp.tool(
    description=(
        "Update source fields (patch semantics — only supplied fields change). "
        "Use to enable enrichment post-creation or fix freshness policy. "
        "enrichment_enabled/taxonomy_id/model: enrichment config. "
        "freshness_policy: none|automatic|manual. "
        "Returns updated source dict including enrichment fields."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_update_source(
    source_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enrichment_enabled: Optional[bool] = None,
    enrichment_taxonomy_id: Optional[str] = None,
    enrichment_model: Optional[str] = None,
    freshness_policy: Optional[str] = None,
    stale_after_days: Optional[int] = None,
    refresh_interval_days: Optional[int] = None,
    youtube_backfill_mode: Optional[str] = None,
    youtube_recent_count: Optional[int] = None,
    path_prefix: Optional[str] = None,
    path_excludes: Optional[list[str]] = None,
) -> dict:
    """Update an existing source. Only supplied fields are modified.

    Returns:
        dict with the same keys as agentbase_get_source on success, including updated
        enrichment_enabled, enrichment_taxonomy_id, enrichment_model,
        freshness_policy, stale_after_days, refresh_interval_days, next_refresh_at.
        On error: {"error": str}
    """
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = IngestionService(db)
        try:
            source = await service.update_source(
                source_id=source_id,
                name=name,
                description=description,
                enrichment_enabled=enrichment_enabled,
                enrichment_taxonomy_id=enrichment_taxonomy_id,
                enrichment_model=enrichment_model,
                freshness_policy=freshness_policy,
                stale_after_days=stale_after_days,
                refresh_interval_days=refresh_interval_days,
                youtube_backfill_mode=youtube_backfill_mode,
                youtube_recent_count=youtube_recent_count,
                path_prefix=path_prefix,
                path_excludes=path_excludes,
            )
            await db.commit()
            logger.info("MCP: Updated source", source_id=source_id)
            await publish_source_event("updated", source_id, {"name": source.name}, source="mcp")
            result = _source_to_dict(source)
            from app.api.sources.helpers import get_sub_source_document_counts
            sub_doc_counts = await get_sub_source_document_counts(db, [source])
            if source.id in sub_doc_counts:
                result["document_count"] = sub_doc_counts[source.id]
            return result
        except ValueError as e:
            return {"error": str(e)}


# ============================================================
# Indexing
# ============================================================

@mcp.tool(
    description=(
        "Start indexing a source (runs in background). "
        "Poll agentbase_get_source_status to check progress. "
        "Pass force=true to override the 'already_indexing' guard when a previous run has stalled."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_index_source(source_id: str, force: bool = False) -> dict:
    """Trigger background indexing of a source.

    This tool returns immediately; indexing continues in the background after
    the response. No progress notifications are emitted over MCP — poll
    agentbase_get_source_status(source_id) until status is "indexed" or "error".
    Do not call agentbase_index_source again while status is "indexing".

    Args:
        source_id: Source to index.
        force: When True, override the "already_indexing" guard by clearing
            stalled jobs and resetting status. Use to recover from hung jobs.

    Returns:
        dict with keys:
            status (str) - "indexing" once accepted
            source_id (str)
            message (str)
            next_step (str) - how to track completion
            expected_duration (str) - rough duration guidance
        On error: {"error": str}
    """
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = IngestionService(db)

        source = await service.get_source(source_id)
        if not source:
            return {"error": f"Source not found: {source_id}"}

        try:
            status = await service.start_indexing(source_id, force=force)
            if status == "already_indexing":
                return {
                    "status": "indexing",
                    "source_id": source_id,
                    "message": "Indexing already in progress (pass force=true to re-trigger)",
                    "next_step": (
                        "Poll agentbase_get_source_status(source_id) until status is 'indexed' "
                        "or 'error' instead of retrying this call."
                    ),
                }

            await db.commit()

            # Start the indexing task in the background
            task = asyncio.create_task(run_indexing_task(source_id))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

            logger.info("MCP: Started indexing", source_id=source_id)
            # Publish event for UI update
            await publish_source_event("indexing", source_id, {"name": source.name}, source="mcp")
            return {
                "status": "indexing",
                "source_id": source_id,
                "message": "Indexing started in background",
                "next_step": (
                    "Poll agentbase_get_source_status(source_id) until status is 'indexed' or "
                    "'error'. Do not call agentbase_index_source again while status is 'indexing'."
                ),
                "expected_duration": (
                    "Seconds for small sources; minutes to hours for large sites "
                    "or directories."
                ),
            }
        except ValueError as e:
            return {"error": str(e)}


@mcp.tool(
    description="Get indexing status, progress, and errors for a source. Poll this after agentbase_index_source.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_source_status(source_id: str) -> dict:
    """Get indexing status, progress, and errors for a source.

    Returns:
        dict with keys:
            source_id (str), status (str - pending/indexing/indexed/error),
            progress (int|None), progress_total (int|None),
            progress_message (str|None), document_count (int),
            chunk_count (int), error_message (str|None)
        On error: {"error": str}
    """
    async with async_session_maker() as db:
        service = IngestionService(db)

        try:
            status = await service.get_indexing_status(source_id)
            return {
                "source_id": status.source_id,
                "status": status.status,
                "progress": status.progress,
                "progress_total": status.progress_total,
                "progress_message": status.progress_message,
                "document_count": status.document_count,
                "chunk_count": status.chunk_count,
                "error_message": status.error_message,
            }
        except ValueError as e:
            return {"error": str(e)}


# ============================================================
# Search
# ============================================================

@mcp.tool(
    description=(
        "Search indexed content with hybrid (semantic + keyword) search. "
        "Scope with source_ids or knowledge_base_id (library). "
        "Use agentbase_list_filter_fields/agentbase_list_filter_values to discover metadata filters. "
        "For complex multi-part questions, use agentbase_deep_search instead."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_search_sources(
    query: Annotated[str, Field(
        min_length=1, max_length=2000,
        description="Natural-language search query",
    )],
    project_id: Optional[str] = None,
    source_ids: Optional[list[str]] = None,
    knowledge_base_id: Optional[str] = None,
    top_k: Annotated[int, Field(
        ge=1, le=50, description="Number of results to return",
    )] = 5,
    hybrid: bool = True,
    vector_weight: Annotated[float, Field(
        ge=0.0, le=1.0,
        description="Weight of vector vs keyword scores in hybrid mode",
    )] = 0.7,
    filters: Optional[dict] = None,
    rerank: bool = True,
    include_neighbors: Annotated[int, Field(
        ge=0, le=10,
        description="Neighboring chunks to include per result",
    )] = 0,
) -> list[dict]:
    """Search indexed content with hybrid semantic + keyword search.

    Returns:
        list[dict] where each dict has keys:
            content (str) - matched chunk text
            source (str) - document URL or file path
            score (float) - vector similarity score (0-1)
            title (str) - document title
            source_name (str) - parent source name
            document_path (str) - original document path
            collection (str) - Qdrant collection name
            rerank_score (float|None) - cross-encoder rerank score when rerank=True
            metadata (dict) - chunk metadata (platforms, topics, etc.)
            context_chunks (list[dict]|None) - neighboring chunks when include_neighbors > 0
        On error: [{"error": str}]
    """
    # Cross-field check (single-field constraints are enforced by Field() metadata)
    if source_ids and knowledge_base_id:
        return [{"error": "source_ids and knowledge_base_id are mutually exclusive"}]
    async with async_session_maker() as db:
        rag_service = RAGService(db)

        try:
            if hybrid:
                results = await rag_service.search_hybrid(
                    query=query,
                    project_id=project_id,
                    top_k=top_k,
                    vector_weight=vector_weight,
                    filters=filters,
                    source_ids=source_ids,
                    knowledge_base_id=knowledge_base_id,
                    rerank=rerank,
                )
            else:
                results = await rag_service.search(
                    query=query,
                    project_id=project_id,
                    top_k=top_k,
                    source_ids=source_ids,
                    knowledge_base_id=knowledge_base_id,
                    filters=filters,
                    rerank=rerank,
                )

            logger.info(
                "MCP: Knowledge search",
                query=query[:50],
                results=len(results),
                source_ids=source_ids,
                rerank=rerank,
                include_neighbors=include_neighbors,
            )

            # Fetch neighboring chunks in parallel when requested
            from app.services.rag.neighbors import fetch_chunk_neighbors

            neighbor_lists: list[list[dict] | None] = [None] * len(results)
            if include_neighbors > 0 and results:
                async def _fetch(idx: int, r) -> tuple[int, list[dict] | None]:
                    try:
                        chunks = await fetch_chunk_neighbors(
                            client=rag_service.client,
                            collection=r.collection,
                            metadata=r.metadata,
                            chunk_index=r.metadata.get("chunk_index"),
                            window_size=include_neighbors,
                        )
                        return idx, chunks
                    except Exception as exc:
                        logger.warning(
                            "MCP: fetch_chunk_neighbors failed",
                            collection=r.collection,
                            chunk_index=r.metadata.get("chunk_index"),
                            error=str(exc),
                        )
                        return idx, None

                fetched = await asyncio.gather(
                    *[_fetch(i, r) for i, r in enumerate(results)]
                )
                for idx, chunks in fetched:
                    neighbor_lists[idx] = chunks

            # Build output dicts
            output = []
            for i, r in enumerate(results):
                item = {
                    "content": r.content,
                    "source": r.source,
                    "score": r.score,
                    "title": r.title,
                    "source_name": r.source_name,
                    "document_path": r.document_path,
                    "collection": r.collection,
                    "rerank_score": r.rerank_score,
                    "metadata": r.metadata,
                }
                if include_neighbors > 0:
                    item["context_chunks"] = neighbor_lists[i]
                output.append(item)

            return [_sanitize_for_json(item) for item in output]
        except Exception as e:
            logger.error("MCP: Knowledge search failed", error=str(e))
            return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool(
    description=(
        "Deep search for complex multi-part questions. Decomposes query into sub-queries, "
        "searches in parallel, fuses via RRF, and reranks. Use instead of agentbase_search_sources "
        "when question spans multiple entities or aspects. Adds 1-3s latency."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_deep_search(
    query: Annotated[str, Field(
        min_length=1, max_length=2000,
        description="Complex or multi-part question to decompose and search",
    )],
    source_ids: Optional[list[str]] = None,
    knowledge_base_id: Optional[str] = None,
    top_k: Annotated[int, Field(
        ge=1, le=50, description="Number of fused results to return",
    )] = 10,
    max_sub_queries: Annotated[int, Field(
        ge=1, le=10, description="Maximum sub-queries to decompose into",
    )] = 5,
    filters: Optional[dict] = None,
    rerank: bool = True,
    include_decomposition: bool = False,
) -> dict:
    """Deep search with automatic query decomposition for multi-part questions.

    Returns:
        dict with keys:
            results (list[dict]) - each with: content (str), source (str),
                score (float), title (str), source_name (str),
                document_path (str), collection (str),
                rerank_score (float|None), metadata (dict)
            stats (dict) - sub_query_count (int), total_candidates (int),
                total_time_ms (int), decompose_time_ms (int),
                search_time_ms (int), rerank_time_ms (int|None)
            sub_queries (list[dict]|None) - only when include_decomposition=True;
                each with: query (str), filters (dict|None), strategy (str)
        On error: {"error": str, "results": [], "stats": {}}
    """
    # Cross-field check (top_k / max_sub_queries ranges are enforced by Field() metadata)
    if source_ids and knowledge_base_id:
        return {"error": "source_ids and knowledge_base_id are mutually exclusive", "results": [], "stats": {}}

    async with async_session_maker() as db:
        rag_service = RAGService(db)

        try:
            result = await rag_service.deep_search(
                query=query,
                top_k=top_k,
                max_sub_queries=max_sub_queries,
                filters=filters,
                source_ids=source_ids,
                knowledge_base_id=knowledge_base_id,
                rerank=rerank,
                include_decomposition=include_decomposition,
            )

            logger.info(
                "MCP: Deep search",
                query=query[:50],
                sub_queries=result.stats.get("sub_query_count"),
                candidates=result.stats.get("total_candidates"),
                returned=len(result.results),
                total_ms=result.stats.get("total_time_ms"),
            )

            output = {
                "results": [
                    {
                        "content": r.content,
                        "source": r.source,
                        "score": r.score,
                        "title": r.title,
                        "source_name": r.source_name,
                        "document_path": r.document_path,
                        "collection": r.collection,
                        "rerank_score": r.rerank_score,
                        "metadata": r.metadata,
                    }
                    for r in result.results
                ],
                "stats": result.stats,
            }

            if include_decomposition:
                output["sub_queries"] = [
                    {
                        "query": sq.query,
                        "filters": sq.filters,
                        "strategy": sq.strategy,
                    }
                    for sq in result.sub_queries
                ]

            return _sanitize_for_json(output)
        except Exception as e:
            logger.error("MCP: Deep search failed", error=str(e))
            return {"error": f"Deep search failed: {str(e)}", "results": [], "stats": {}}


# ============================================================
# Filter Discovery
# ============================================================

@mcp.tool(
    description=(
        "List unique values for a metadata filter field. "
        "Call agentbase_list_filter_fields first to see available fields. "
        "Use results to build filters for agentbase_search_sources."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_list_filter_values(
    field: str,
    source_ids: Optional[list[str]] = None,
) -> dict:
    """List unique values for a filterable field. Returns {field, values, count}."""
    from app.services.rag.neighbors import list_unique_field_values
    from app.services.rag.client import get_qdrant_client
    from sqlalchemy import select as sa_select
    from app.models import Source

    async with async_session_maker() as db:
        try:
            client = get_qdrant_client()

            # Resolve collections to search
            if source_ids:
                stmt = sa_select(Source).where(
                    Source.id.in_(source_ids),
                    Source.status == "indexed",
                )
            else:
                stmt = sa_select(Source).where(
                    Source.status == "indexed"
                )
            result = await db.execute(stmt)
            sources = list(result.scalars().all())

            collections = [s.collection_name for s in sources if s.collection_name]
            if not collections:
                return {"field": field, "values": [], "count": 0}

            values = await list_unique_field_values(client, field, collections)
            return {"field": field, "values": values, "count": len(values)}

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error("MCP: agentbase_list_filter_values failed", field=field, error=str(e))
            return {"error": f"Failed to list values for '{field}': {str(e)}"}


@mcp.tool(
    description="List available metadata filter fields for agentbase_search_sources. Call before agentbase_list_filter_values.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_list_filter_fields() -> dict:
    """List all filterable metadata fields."""
    return {
        "fields": [
            {
                "name": "platforms",
                "description": "Technology platforms (e.g. a CRM, CDP, or marketing platform)",
            },
            {
                "name": "products",
                "description": "Specific products within a platform (e.g. its individual modules or editions)",
            },
            {
                "name": "offerings",
                "description": "Service or solution offerings (e.g. Integration, Analytics, Automation)",
            },
            {
                "name": "doc_category",
                "description": "Document category (e.g. proposal, research, product_overview, case_study)",
            },
            {
                "name": "companies",
                "description": "Companies mentioned or associated with the document",
            },
            {
                "name": "topics",
                "description": "Topics covered in the document (e.g. strategy, use_cases, architecture)",
            },
            {
                "name": "document_type",
                "description": "Type of document (e.g. presentation, report, whitepaper)",
            },
            {
                "name": "file_type",
                "description": "File extension of the source file (e.g. pdf, docx, html, pptx)",
            },
        ],
        "usage": (
            "Pass any of these as keys in the filters dict when calling agentbase_search_sources. "
            "Filters AND across keys, OR within a key's list. "
            "Use agentbase_list_filter_values(field='platforms') to discover valid values."
        ),
    }


# Import sibling modules so their @mcp.tool() decorators register
# when server.py does `from app.mcp.tools import sources`
import app.mcp.tools.sources_upload  # noqa: E402, F401
import app.mcp.tools.sources_docs  # noqa: E402, F401
