"""
MCP Tools for Library Management

CRUD and source management for Libraries. Each Library owns a Qdrant
collection and aggregates multiple Sources. Libraries are the preferred
unit for binding knowledge to agents.
"""

from typing import Annotated, Optional

import structlog
from pydantic import Field

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.core.auth import Scope, check_mcp_scope

logger = structlog.get_logger()


def _build_domain_summary(kb) -> str:
    """Build a one-line domain summary for external agent discovery."""
    parts = []
    if kb.description:
        desc = kb.description[:100]
        if len(kb.description) > 100:
            desc = desc.rsplit(" ", 1)[0] + "..."
        parts.append(desc)
    parts.append(f"{kb.name}. {kb.chunk_count or 0} chunks across {kb.source_count or 0} sources.")
    return " ".join(parts)


def _library_to_dict(kb) -> dict:
    """Convert KnowledgeBase ORM model to dict."""
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "domain_summary": _build_domain_summary(kb),
        "project_id": kb.project_id,
        "collection_name": kb.collection_name,
        "embedding_provider": kb.embedding_provider,
        "embedding_model": kb.embedding_model,
        "embedding_dimensions": kb.embedding_dimensions,
        "taxonomy_id": kb.taxonomy_id,
        "enrichment_model": kb.enrichment_model,
        "source_count": kb.source_count,
        "document_count": kb.document_count,
        "chunk_count": kb.chunk_count,
        "status": kb.status,
        "source_ids": [s.id for s in (kb.sources or [])],
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
        "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
    }


# ============================================================
# Library CRUD
# ============================================================

@mcp.tool(
    description="List all libraries with pagination. Optional project_id filter. Each library owns a Qdrant collection. Supports limit/offset pagination (default: limit=50, offset=0).",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_libraries(project_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    """List all libraries with pagination.

    Returns:
        dict with keys:
            total (int) - total number of libraries matching the filter,
            count (int) - number of items in this page,
            offset (int) - current offset,
            has_more (bool) - whether more items exist beyond this page,
            next_offset (int|None) - offset for the next page, or None if no more,
            items (list[dict]) - list of library dicts, each with keys:
                id (str), name (str), description (str|None), project_id (str|None),
                collection_name (str|None), embedding_provider (str|None),
                embedding_model (str|None), embedding_dimensions (int|None),
                taxonomy_id (str|None), enrichment_model (str|None),
                source_count (int), document_count (int), chunk_count (int),
                status (str), source_ids (list[str]),
                created_at (str - ISO datetime), updated_at (str - ISO datetime)
        On error: {"error": str}
    """
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            kbs = await svc.list_kbs(project_id=project_id)
            total = len(kbs)
            page = kbs[offset:offset + limit]
            items = [_library_to_dict(kb) for kb in page]
            return {
                "total": total,
                "count": len(items),
                "offset": offset,
                "has_more": offset + len(items) < total,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "items": items,
            }
        except Exception as e:
            return {"error": f"Failed to list libraries: {str(e)}"}


@mcp.tool(
    description="Get a library by ID with source list and stats.",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_get_library(library_id: str) -> dict:
    """Get library details including source list, stats, and configuration.

    Returns:
        dict with keys:
            id (str), name (str), description (str|None), project_id (str|None),
            collection_name (str|None), embedding_provider (str|None),
            embedding_model (str|None), embedding_dimensions (int|None),
            taxonomy_id (str|None), enrichment_model (str|None),
            source_count (int), document_count (int), chunk_count (int),
            status (str), source_ids (list[str]),
            created_at (str - ISO datetime), updated_at (str - ISO datetime)
        On error: {"error": str}
    """
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            kb = await svc.get_kb(library_id)
            if not kb:
                return {"error": f"Library not found: {library_id}"}
            return _library_to_dict(kb)
        except Exception as e:
            return {"error": f"Failed to get library: {str(e)}"}


@mcp.tool(
    description=(
        "Create a library. If embedding_provider/embedding_model are omitted, "
        "the library defers its embedding config and locks it in when the first "
        "source is added. Optional: taxonomy_id for auto-classification."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_create_library(
    name: Annotated[str, Field(
        min_length=1, max_length=255,
        description="Display name, e.g. 'ACME Sales Playbook'",
    )],
    embedding_provider: Annotated[Optional[str], Field(max_length=50)] = None,
    embedding_model: Annotated[Optional[str], Field(max_length=100)] = None,
    description: Optional[str] = None,
    project_id: Optional[str] = None,
    embedding_dimensions: Annotated[Optional[int], Field(ge=1, le=16384)] = None,
    taxonomy_id: Optional[str] = None,
    enrichment_model: Annotated[Optional[str], Field(max_length=100)] = None,
) -> dict:
    """Create a new library."""
    check_mcp_scope(Scope.WRITE)
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            kb = await svc.create_kb(
                name=name,
                description=description,
                project_id=project_id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
                taxonomy_id=taxonomy_id,
                enrichment_model=enrichment_model,
            )
            logger.info("MCP: Created library", library_id=kb.id, name=name)
            return _library_to_dict(kb)
        except Exception as e:
            return {"error": f"Failed to create library: {str(e)}"}


@mcp.tool(
    description="Update a library's metadata. Pass only the fields you want to change.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_update_library(
    library_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    taxonomy_id: Optional[str] = None,
    enrichment_model: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Update a library."""
    check_mcp_scope(Scope.WRITE)
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            updates = {}
            if name is not None:
                updates["name"] = name
            if description is not None:
                updates["description"] = description
            if taxonomy_id is not None:
                updates["taxonomy_id"] = taxonomy_id
            if enrichment_model is not None:
                updates["enrichment_model"] = enrichment_model
            if status is not None:
                updates["status"] = status

            kb = await svc.update_kb(library_id, **updates)
            if not kb:
                return {"error": f"Library not found: {library_id}"}
            logger.info("MCP: Updated library", library_id=library_id)
            return _library_to_dict(kb)
        except Exception as e:
            return {"error": f"Failed to update library: {str(e)}"}


@mcp.tool(
    description=(
        "Delete a library, its Qdrant collection, and document records. Irreversible. "
        "Sources are NOT deleted — only the library and its indexed data."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_delete_library(library_id: str) -> dict:
    """Delete a library."""
    check_mcp_scope(Scope.WRITE)
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            deleted = await svc.delete_kb(library_id)
            if not deleted:
                return {"error": f"Library not found: {library_id}"}
            logger.info("MCP: Deleted library", library_id=library_id)
            return {"status": "deleted", "id": library_id}
        except Exception as e:
            return {"error": f"Failed to delete library: {str(e)}"}


# ============================================================
# Source Management
# ============================================================

@mcp.tool(
    description=(
        "Add a source to a library. Embedding models must be compatible. "
        "Index the source first, then add it here."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_add_source_to_library(
    library_id: str,
    source_id: str,
) -> dict:
    """Associate a source with a library.

    Libraries lock their embedding model to the first source bound to them.
    Subsequent sources must have a matching embedding model, or this tool
    returns an error dict with ``error_code: "EMBEDDING_MISMATCH"`` and the
    full ``library`` / ``source`` / ``suggested_action`` fields so an external
    agent can adapt — typically by creating a new source with a matching model.
    """
    check_mcp_scope(Scope.WRITE)
    from app.services.library import LibraryService
    from app.services.library.service import EmbeddingMismatchError

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            result = await svc.add_source(library_id, source_id)
            if result is None:
                return {"error": "Library or source not found", "error_code": "NOT_FOUND"}
            logger.info(
                "MCP: Added source to library",
                library_id=library_id,
                source_id=source_id,
                reindex_queued=result.get("reindex_queued"),
            )
            return {
                "status": "added",
                "library_id": library_id,
                "source_id": source_id,
                "already_bound": result.get("already_bound", False),
                "reindex_queued": result.get("reindex_queued", False),
            }
        except EmbeddingMismatchError as exc:
            logger.info("MCP: Embedding mismatch", library_id=library_id, source_id=source_id)
            payload = exc.to_dict()
            payload["error"] = payload["detail"]
            return payload
        except Exception as e:
            return {"error": f"Failed to add source to library: {str(e)}"}


@mcp.tool(
    description=(
        "Remove a source from a library. Deletes its documents from the library. "
        "The source itself is NOT deleted."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_remove_source_from_library(
    library_id: str,
    source_id: str,
) -> dict:
    """Remove a source from a library."""
    check_mcp_scope(Scope.WRITE)
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            ok = await svc.remove_source(library_id, source_id)
            if not ok:
                return {"error": f"Source {source_id} not found in library {library_id}"}
            logger.info("MCP: Removed source from library", library_id=library_id, source_id=source_id)
            return {"status": "removed", "library_id": library_id, "source_id": source_id}
        except Exception as e:
            return {"error": f"Failed to remove source from library: {str(e)}"}


@mcp.tool(
    description="Recalculate a library's source/document/chunk counts from actual data. Use if stats look stale.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_recalculate_library_stats(library_id: str) -> dict:
    """Recalculate stats for a library."""
    check_mcp_scope(Scope.WRITE)
    from app.services.library import LibraryService

    async with async_session_maker() as db:
        try:
            svc = LibraryService(db)
            kb = await svc.recalculate_stats(library_id)
            if not kb:
                return {"error": f"Library not found: {library_id}"}
            logger.info("MCP: Recalculated library stats", library_id=library_id)
            return _library_to_dict(kb)
        except Exception as e:
            return {"error": f"Failed to recalculate stats: {str(e)}"}
