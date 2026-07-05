"""
MCP Tools for Source Operations

Provides tools for:
- Source analytics (system-wide statistics)
- Source operations: refresh, re-enrich, retry failed URLs
- Watcher management: status, start, stop, force sync
- Freshness & coverage analysis
"""

from typing import Optional
import structlog

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.core.auth import Scope, check_mcp_scope

logger = structlog.get_logger()


# ============================================================
# URL Scanning (precursor to source creation)
# ============================================================

@mcp.tool(
    description=(
        "Scan a URL to discover page structure before creating a source. "
        "Modes: auto_discover_sitemap, provide sitemap_url, or crawl. "
        "Returns page tree with URLs. Use returned URLs as selected_urls in agentbase_create_source."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def agentbase_scan_url(
    url: str,
    max_depth: int = 2,
    path_scope: Optional[str] = None,
    sitemap_url: Optional[str] = None,
    path_filter: Optional[str] = None,
    auto_discover_sitemap: bool = False,
) -> dict:
    """Scan a URL and return site tree structure for source creation.

    This call is synchronous: it returns only when the scan completes and
    emits no intermediate progress. Sitemap modes (auto_discover_sitemap or
    sitemap_url) usually finish in seconds; crawl mode with max_depth >= 3
    can take a minute or more on large sites. Do not retry while a scan is
    running — wait for the response.

    Returns:
        dict with keys:
            tree (dict) - nested {url, title, path, children} structure
            sitemap_url (str|None) - sitemap used, if any
            total_urls (int) - number of discovered URLs
            urls (list[str]) - flat list for use as selected_urls in agentbase_create_source
        On error: {"error": str}
    """
    check_mcp_scope(Scope.READ)
    from app.services import IngestionService

    async with async_session_maker() as db:
        service = IngestionService(db)
        try:
            result = await service.scan_url(
                url=url,
                max_depth=max_depth,
                path_scope=path_scope,
                sitemap_url=sitemap_url,
                path_filter=path_filter,
                auto_discover_sitemap=auto_discover_sitemap,
            )

            def tree_to_dict(node) -> dict:
                return {
                    "url": node.url,
                    "title": node.title,
                    "path": node.path,
                    "children": [tree_to_dict(c) for c in node.children],
                }

            flat_urls = []
            def collect_urls(node):
                flat_urls.append(node.url)
                for c in node.children:
                    collect_urls(c)
            collect_urls(result.tree)

            return {
                "tree": tree_to_dict(result.tree),
                "sitemap_url": result.sitemap_url,
                "total_urls": len(flat_urls),
                "urls": flat_urls,
            }
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error("MCP: agentbase_scan_url failed", url=url, error=str(e))
            return {"error": f"Scan failed: {str(e)}"}


# ============================================================
# Knowledge Analytics
# ============================================================

@mcp.tool(
    description=(
        "Get system-wide analytics: source/document/chunk counts, embedding distribution, "
        "classification coverage, Qdrant health. Good first call to assess system state."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_source_analytics() -> dict:
    """Get system-wide analytics across all sources and storage.

    Returns:
        dict with keys:
            summary (dict) - total_sources (int), indexed_sources (int),
                total_documents (int), total_chunks (int),
                total_qdrant_points (int), libraries (int),
                active_watchers (int), sources_with_enrichment (int)
            sources_by_type (dict[str, int]) - e.g. {"url": 5, "file": 3}
            sources_by_status (dict[str, int]) - e.g. {"indexed": 6, "error": 1}
            top_sources (list[dict]) - top 10 by chunk count; each with
                name (str), chunks (int), documents (int)
            embedding_models (dict[str, int]) - e.g. {"ollama/qwen3-embedding:4b": 8}
            classification_coverage (dict) - classified_chunks (int),
                total_chunks (int), coverage_percent (float)
            storage (dict) - qdrant_collections (int),
                total_qdrant_points (int)
        On error: {"error": str}
    """
    from sqlalchemy import select, func, case
    from app.models import Source, Library, Document
    from app.services.ingestion.watcher import watcher_manager

    async with async_session_maker() as db:
        try:
            # Core aggregates
            agg_stmt = select(
                func.count(Source.id).label("total_sources"),
                func.sum(
                    case((Source.status == "indexed", 1), else_=0)
                ).label("indexed_sources"),
                func.sum(Source.document_count).label("total_documents"),
                func.sum(Source.chunk_count).label("total_chunks"),
                func.sum(
                    case((Source.enrichment_enabled.is_(True), 1), else_=0)
                ).label("sources_with_enrichment"),
            )
            agg_result = await db.execute(agg_stmt)
            agg_row = agg_result.one()

            total_sources = int(agg_row.total_sources or 0)
            indexed_sources = int(agg_row.indexed_sources or 0)
            total_documents = int(agg_row.total_documents or 0)
            total_chunks = int(agg_row.total_chunks or 0)
            sources_with_enrichment = int(agg_row.sources_with_enrichment or 0)

            # Sources by type
            type_result = await db.execute(
                select(Source.source_type, func.count(Source.id).label("cnt"))
                .group_by(Source.source_type)
            )
            sources_by_type = {row.source_type: row.cnt for row in type_result.all()}

            # Sources by status
            status_result = await db.execute(
                select(Source.status, func.count(Source.id).label("cnt"))
                .group_by(Source.status)
            )
            sources_by_status = {row.status: row.cnt for row in status_result.all()}

            # Top 10 sources by chunk count
            top_result = await db.execute(
                select(Source.name, Source.chunk_count, Source.document_count)
                .order_by(Source.chunk_count.desc())
                .limit(10)
            )
            top_sources = [
                {"name": row.name, "chunks": row.chunk_count, "documents": row.document_count}
                for row in top_result.all()
            ]

            # Embedding model distribution
            emb_result = await db.execute(
                select(
                    Source.embedding_provider,
                    Source.embedding_model,
                    func.count(Source.id).label("cnt"),
                )
                .where(Source.embedding_model.isnot(None))
                .group_by(Source.embedding_provider, Source.embedding_model)
            )
            embedding_models = {}
            for row in emb_result.all():
                provider = row.embedding_provider or ""
                model = row.embedding_model or ""
                key = f"{provider}/{model}" if provider else model
                embedding_models[key] = row.cnt

            # Library count
            kb_result = await db.execute(select(func.count(Library.id)))
            libraries = int(kb_result.scalar() or 0)

            # Active watchers
            try:
                active_watchers = len(watcher_manager.get_all_statuses())
            except Exception:
                active_watchers = 0

            # Qdrant stats
            total_qdrant_points = 0
            qdrant_collections = 0
            try:
                from app.services.ingestion_service import get_qdrant_client
                client = get_qdrant_client()
                collections_response = client.get_collections()
                qdrant_collections = len(collections_response.collections)
                for col in collections_response.collections:
                    try:
                        info = client.get_collection(col.name)
                        total_qdrant_points += info.points_count or 0
                    except Exception:
                        pass
            except Exception as qdrant_err:
                logger.warning("MCP: Qdrant unavailable for analytics", error=str(qdrant_err))

            # Classification coverage
            # Sum chunk_count from Document rows with a non-null
            # classification (written by the enrichment pipeline).
            classified_chunks = 0
            try:
                classified_result = await db.execute(
                    select(func.sum(Document.chunk_count)).where(
                        Document.classification.isnot(None)
                    )
                )
                classified_chunks = int(classified_result.scalar() or 0)
            except Exception:
                pass

            coverage_percent = (
                round((classified_chunks / total_chunks) * 100, 1)
                if total_chunks > 0
                else 0.0
            )

            return {
                "summary": {
                    "total_sources": total_sources,
                    "indexed_sources": indexed_sources,
                    "total_documents": total_documents,
                    "total_chunks": total_chunks,
                    "total_qdrant_points": total_qdrant_points,
                    "libraries": libraries,
                    "active_watchers": active_watchers,
                    "sources_with_enrichment": sources_with_enrichment,
                },
                "sources_by_type": sources_by_type,
                "sources_by_status": sources_by_status,
                "top_sources": top_sources,
                "embedding_models": embedding_models,
                "classification_coverage": {
                    "classified_chunks": classified_chunks,
                    "total_chunks": total_chunks,
                    "coverage_percent": coverage_percent,
                },
                "storage": {
                    "qdrant_collections": qdrant_collections,
                    "total_qdrant_points": total_qdrant_points,
                },
            }
        except Exception as e:
            logger.error("MCP: Analytics failed", error=str(e))
            return {"error": f"Analytics failed: {str(e)}"}


# ============================================================
# Source Operations: Refresh, Re-Enrich, Retry Failed
# ============================================================

@mcp.tool(
    description=(
        "Re-index a source. mode='full' (default) clears and re-indexes everything. "
        "mode='selective' re-indexes specific URLs only. For just failed URLs, use agentbase_retry_failed_urls. "
        "Pass force=true to override the 'already_indexing' guard when a previous run has stalled."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_refresh_source(
    source_id: str,
    mode: str = "full",
    urls: Optional[list[str]] = None,
    force: bool = False,
) -> dict:
    """Re-index a source. Returns job_id for tracking.

    This tool returns immediately; re-indexing runs as a background job after
    the response. No progress notifications are emitted over MCP — poll
    agentbase_get_source_status(source_id) or agentbase_get_indexing_queue() until status is
    "indexed" or "error". Do not call agentbase_refresh_source again while status is
    "indexing".

    Args:
        source_id: Source to refresh.
        mode: "full" (re-index everything) or "selective" (only specified urls).
        urls: Required when mode="selective".
        force: When True, override the "already_indexing" guard by clearing
            stalled jobs and resetting status. Use to recover from hung jobs.

    Returns:
        dict with keys:
            status (str) - "indexing" once accepted
            source_id (str)
            job_id (str) - background job id, visible in agentbase_get_indexing_queue
            message (str), mode (str)
            url_count (int) - selective mode only
            next_step (str) - how to track completion
            expected_duration (str) - rough duration guidance
        On error: {"error": str}
    """
    check_mcp_scope(Scope.WRITE)
    from app.services import IngestionService
    from app.services.job_service import JobService
    from sqlalchemy import update
    from app.models import IndexingLog

    async with async_session_maker() as db:
        service = IngestionService(db)
        job_service = JobService(db)

        source = await service.get_source(source_id)
        if not source:
            return {"error": f"Source not found: {source_id}"}

        if source.source_type == "collection":
            return {"error": "Cannot refresh an adopted Qdrant collection — data is managed externally."}

        if source.status == "indexing" and not force:
            return {
                "status": "indexing",
                "source_id": source_id,
                "message": "Indexing already in progress (pass force=true to re-trigger)",
                "next_step": (
                    "Poll agentbase_get_source_status(source_id) until status is 'indexed' "
                    "or 'error' instead of retrying this call."
                ),
            }

        if mode == "selective":
            if source.source_type != "url":
                return {"error": "Selective refresh only available for URL sources"}
            if not urls:
                return {"error": "Must specify urls for selective refresh"}

            # Reset log status for the specified URLs
            await db.execute(
                update(IndexingLog)
                .where(IndexingLog.source_id == source_id, IndexingLog.url.in_(urls))
                .values(status="pending", error_message=None,
                        scrape_duration_ms=None, embed_duration_ms=None)
            )
            await service.start_indexing(source_id, force=force)
            job = await job_service.enqueue(
                "selective_index",
                {"source_id": source_id, "urls": urls},
                project_id=source.project_id,
            )
            await db.commit()

            logger.info("MCP: Selective refresh started", source_id=source_id, url_count=len(urls))
            return {
                "status": "indexing",
                "source_id": source_id,
                "job_id": job.id,
                "message": f"Selective refresh started for {len(urls)} URLs",
                "mode": "selective",
                "url_count": len(urls),
                "next_step": (
                    "Poll agentbase_get_source_status(source_id) or agentbase_get_indexing_queue() until "
                    "status is 'indexed' or 'error'. Do not call agentbase_refresh_source again "
                    "while status is 'indexing'."
                ),
                "expected_duration": (
                    "Roughly a few seconds per URL; scales with url_count."
                ),
            }

        # Full refresh
        await service.start_indexing(source_id, force=force)
        job = await job_service.enqueue(
            "index_source",
            {"source_id": source_id},
            project_id=source.project_id,
        )
        await db.commit()

        logger.info("MCP: Full refresh started", source_id=source_id)
        return {
            "status": "indexing",
            "source_id": source_id,
            "job_id": job.id,
            "message": "Full refresh started",
            "mode": "full",
            "next_step": (
                "Poll agentbase_get_source_status(source_id) or agentbase_get_indexing_queue() until "
                "status is 'indexed' or 'error'. Do not call agentbase_refresh_source again "
                "while status is 'indexing'."
            ),
            "expected_duration": (
                "Minutes for small sources; up to hours for large sites or directories."
            ),
        }


@mcp.tool(
    description=(
        "Re-classify all chunks in a source using LLM enrichment. "
        "Source must be indexed with an enrichment taxonomy configured. "
        "Use after updating taxonomy terms."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_re_enrich_source(source_id: str) -> dict:
    """Trigger re-enrichment. Returns job_id for tracking.

    This tool returns immediately; re-classification runs as a background job
    after the response. No progress notifications are emitted over MCP — poll
    agentbase_get_source_status(source_id) until status returns to "indexed". Do not
    call agentbase_re_enrich_source again while status is "indexing".

    Returns:
        dict with keys:
            status (str) - "queued" once accepted
            source_id (str)
            job_id (str) - background job id, visible in agentbase_get_indexing_queue
            message (str)
            next_step (str) - how to track completion
            expected_duration (str) - rough duration guidance
        On error: {"error": str}
    """
    check_mcp_scope(Scope.WRITE)
    from datetime import datetime
    from app.services import IngestionService
    from app.services.job_service import JobService

    async with async_session_maker() as db:
        service = IngestionService(db)
        source = await service.get_source(source_id)
        if not source:
            return {"error": f"Source not found: {source_id}"}

        if not source.collection_name:
            return {
                "error": "Source has no Qdrant collection. Index the source first before re-enriching."
            }

        if not source.enrichment_taxonomy_id:
            return {
                "error": (
                    "Source has no enrichment taxonomy configured. "
                    "Set enrichment_taxonomy_id on the source before re-enriching."
                )
            }

        if source.status == "indexing":
            return {
                "status": "indexing",
                "source_id": source_id,
                "message": "Indexing or enrichment already in progress",
                "next_step": (
                    "Poll agentbase_get_source_status(source_id) until status is 'indexed' "
                    "or 'error' instead of retrying this call."
                ),
            }

        source.status = "indexing"
        source.error_message = None
        source.progress = 0
        source.progress_total = 0
        source.progress_message = "Re-enrichment queued"
        source.progress_updated_at = datetime.utcnow()

        job_service = JobService(db)
        job = await job_service.enqueue(
            "re_enrich_source",
            {"source_id": source_id},
            project_id=source.project_id,
        )
        await db.commit()

        logger.info("MCP: Re-enrichment queued", source_id=source_id, job_id=job.id)
        return {
            "status": "queued",
            "source_id": source_id,
            "job_id": job.id,
            "message": "Re-enrichment job queued",
            "next_step": (
                "Poll agentbase_get_source_status(source_id) until status returns to "
                "'indexed'. Do not call agentbase_re_enrich_source again while status "
                "is 'indexing'."
            ),
            "expected_duration": (
                "LLM classification runs per chunk; expect minutes to hours "
                "for large sources."
            ),
        }


@mcp.tool(
    description=(
        "Retry only failed URLs for a URL source. "
        "Use instead of agentbase_refresh_source when just some pages failed."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_retry_failed_urls(source_id: str) -> dict:
    """Retry failed URLs. Returns job_id and retry_count."""
    check_mcp_scope(Scope.WRITE)
    from app.services import IngestionService
    from app.services.job_service import JobService

    async with async_session_maker() as db:
        service = IngestionService(db)
        job_service = JobService(db)

        try:
            status, retry_count = await service.retry_failed_urls(source_id)
        except ValueError as e:
            return {"error": str(e)}

        if status == "already_indexing":
            return {
                "status": "indexing",
                "source_id": source_id,
                "message": "Indexing already in progress",
            }

        if status == "no_failures":
            return {
                "status": "no_failures",
                "source_id": source_id,
                "message": "No failed URLs to retry",
            }

        failed_logs = await service.get_indexing_logs(source_id, status_filter="pending")
        failed_urls = [log.url for log in failed_logs.logs]

        source = await service.get_source(source_id)
        job = await job_service.enqueue(
            "retry_failed",
            {"source_id": source_id, "urls": failed_urls},
            project_id=source.project_id if source else None,
        )
        await db.commit()

        logger.info("MCP: Retry failed URLs", source_id=source_id, retry_count=retry_count)
        return {
            "status": "indexing",
            "source_id": source_id,
            "job_id": job.id,
            "message": f"Retrying {retry_count} failed URLs",
            "retry_count": retry_count,
        }


# ============================================================
# Watcher Management
# ============================================================

@mcp.tool(
    description="Get status of all active directory file watchers.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_watcher_statuses() -> dict:
    """Get all watcher statuses."""
    from app.services.ingestion.watcher import watcher_manager

    try:
        return {"watchers": watcher_manager.get_all_statuses()}
    except Exception as e:
        return {"error": f"Failed to get watcher statuses: {str(e)}"}


@mcp.tool(
    description="Get file watcher status for a specific directory source.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_watcher_status(source_id: str) -> dict:
    """Get a specific watcher's status."""
    from app.services.ingestion.watcher import watcher_manager

    try:
        status = watcher_manager.get_status(source_id)
        if not status:
            return {"error": f"No active watcher for source: {source_id}"}
        return status
    except Exception as e:
        return {"error": f"Failed to get watcher status: {str(e)}"}


@mcp.tool(
    description="Start file watcher for a directory source. Auto re-indexes on file changes.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_start_watcher(source_id: str) -> dict:
    """Start a directory watcher.

    Sub-sources share the parent root's watcher; passing a sub-source id
    returns an error with the parent's id so callers can retry.
    """
    check_mcp_scope(Scope.WRITE)
    from app.services.ingestion.watcher import watcher_manager
    from app.services import IngestionService

    async with async_session_maker() as db:
        svc = IngestionService(db)
        source = await svc.get_source(source_id)
        if source and getattr(source, "parent_source_id", None):
            return {
                "error": (
                    f"Source {source_id} is a sub-source; start the parent watcher at "
                    f"{source.parent_source_id} instead"
                ),
                "parent_source_id": source.parent_source_id,
            }

    try:
        await watcher_manager.start_watcher(source_id)
        logger.info("MCP: Watcher started", source_id=source_id)
        return {"status": "started", "source_id": source_id}
    except Exception as e:
        return {"error": f"Failed to start watcher: {str(e)}"}


@mcp.tool(
    description="Stop the file watcher for a directory source.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_stop_watcher(source_id: str) -> dict:
    """Stop a directory watcher."""
    check_mcp_scope(Scope.WRITE)
    from app.services.ingestion.watcher import watcher_manager

    try:
        await watcher_manager.stop_watcher(source_id)
        logger.info("MCP: Watcher stopped", source_id=source_id)
        return {"status": "stopped", "source_id": source_id}
    except Exception as e:
        return {"error": f"Failed to stop watcher: {str(e)}"}


@mcp.tool(
    description=(
        "Force immediate directory scan without waiting for the next poll interval. "
        "Refuses to run if the watch root is missing/unreadable, or if the scan would "
        "delete >=90% of the indexed set (broken-mount safety guard). Pass "
        "allow_mass_delete=true only to confirm an intended bulk removal."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_force_sync_watcher(source_id: str, allow_mass_delete: bool = False) -> dict:
    """Force an immediate directory sync."""
    check_mcp_scope(Scope.WRITE)
    from app.services.ingestion.watcher import watcher_manager

    async with async_session_maker() as db:
        try:
            result = await watcher_manager.force_sync(source_id, db, allow_mass_delete=allow_mass_delete)
            logger.info("MCP: Watcher force sync", source_id=source_id, allow_mass_delete=allow_mass_delete)
            return result
        except Exception as e:
            return {"error": f"Force sync failed: {str(e)}"}


# ============================================================
# Freshness & Coverage Analysis
# ============================================================

@mcp.tool(
    description=(
        "List sources approaching or past their staleness threshold. "
        "Only returns sources with freshness_policy 'automatic' or 'manual' "
        "that have a stale_after_days value configured. "
        "Use during library maintenance to identify what needs refreshing. "
        "Stale = past threshold. Aging = within 80% of threshold."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_list_stale_sources(
    library_id: Optional[str] = None,
    freshness_policy: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List sources that need attention based on freshness policy, with pagination.

    Returns:
        dict with keys:
            total (int) - total matching sources before pagination
            count (int) - number of items in this page
            offset (int) - current offset
            has_more (bool) - whether more pages exist
            next_offset (int|None) - offset for next page, None if no more
            items (list[dict]) - stale/aging source dicts from freshness service
    """
    from app.services.freshness_service import list_stale_sources as _list_stale

    async with async_session_maker() as db:
        results = await _list_stale(db, library_id=library_id, policy=freshness_policy)

        total_count = len(results)
        items = results[offset : offset + limit]

        return {
            "total": total_count,
            "count": len(items),
            "offset": offset,
            "has_more": offset + len(items) < total_count,
            "next_offset": offset + len(items) if offset + len(items) < total_count else None,
            "items": items,
        }


@mcp.tool(
    description=(
        "Analyze taxonomy coverage for a library. Returns per-term chunk counts "
        "and coverage ratings: deep (>=20 chunks), adequate (>=10), thin (>=1), "
        "none (0). Requires a taxonomy linked to the library. "
        "Use to identify gaps in a library's knowledge coverage and decide "
        "which topics need more sources."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_library_coverage(library_id: str) -> dict:
    """Coverage gap analysis for a library's taxonomy terms."""
    from app.services.library.coverage import get_library_coverage as _get_coverage

    async with async_session_maker() as db:
        return await _get_coverage(db, library_id)


# ============================================================
# Watcher Event Log
# ============================================================

@mcp.tool(
    description=(
        "List recent watcher events for a directory source. "
        "Returns lifecycle events (started, stopped, recovery) and file events "
        "(created, modified, deleted, error). Useful for diagnosing whether a "
        "folder watcher is active and what files it has processed recently."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_list_watcher_events(
    source_id: str,
    limit: int = 100,
) -> dict:
    """Return watcher event log for a source, newest first."""
    check_mcp_scope(Scope.READ)
    from datetime import datetime as _dt
    from sqlalchemy import select as _select, desc as _desc
    from app.models import WatcherEvent as _WatcherEvent

    async with async_session_maker() as db:
        stmt = (
            _select(_WatcherEvent)
            .where(_WatcherEvent.source_id == source_id)
            .order_by(_desc(_WatcherEvent.timestamp))
            .limit(min(limit, 500))
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        return {
            "source_id": source_id,
            "count": len(rows),
            "events": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "file_path": e.file_path,
                    "message": e.message,
                }
                for e in rows
            ],
        }
