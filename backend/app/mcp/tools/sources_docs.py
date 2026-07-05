"""
MCP Tools for Source Document Operations

Full-document retrieval, document deletion, chunk export, and indexing queue status.
"""

import structlog
from typing import Optional

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.core.auth import Scope, check_mcp_scope
from app.services import IngestionService
from app.services.ingestion import QueueManager
from app.mcp.tools.sources import _sanitize_for_json

logger = structlog.get_logger()


@mcp.tool(
    description=(
        "Get full text of a document by its URL or file path. "
        "Checks Postgres first, falls back to Qdrant chunk reconstruction."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_full_document(
    source_id: str,
    document_source: str,
) -> dict:
    """Retrieve full document text. Returns full_text, title, text_length, retrieved_from."""
    from sqlalchemy import select
    from app.models import Source, ScrapedContent
    from app.services.ingestion.document_ops import DocumentOps

    async with async_session_maker() as db:
        # Resolve source
        stmt = select(Source).where(Source.id == source_id)
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            return {"error": f"Source not found: {source_id}"}

        # 1. Primary: Postgres ScrapedContent
        sc_stmt = select(ScrapedContent).where(
            ScrapedContent.source_id == source_id,
            ScrapedContent.url == document_source,
        )
        sc_result = await db.execute(sc_stmt)
        scraped = sc_result.scalar_one_or_none()

        if scraped:
            return {
                "source_id": source_id,
                "document_source": document_source,
                "title": scraped.title,
                "full_text": scraped.raw_content,
                "text_length": scraped.content_length,
                "content_hash": scraped.content_hash,
                "retrieved_from": "postgres",
            }

        # 2. Fallback: Qdrant scroll reconstruction
        if not source.collection_name:
            return {
                "error": "Source has no Qdrant collection — index it first",
                "source_id": source_id,
            }

        ops = DocumentOps()
        text = await ops.get_document_text_from_qdrant(source.collection_name, document_source)
        metadata = await ops.get_document_metadata(source.collection_name, document_source)

        if not text:
            return {"error": f"Document not found: {document_source}"}

        return {
            "source_id": source_id,
            "document_source": document_source,
            "title": metadata.get("title", ""),
            "full_text": text,
            "text_length": len(text),
            "content_hash": metadata.get("content_hash", ""),
            "retrieved_from": "qdrant_scroll",
            "note": "Reconstructed from chunks — may contain duplicated sentences due to chunk overlap",
        }


@mcp.tool(
    description=(
        "Delete a single document from a source (surgical). "
        "Other documents in the source remain intact. Recalculates stats after."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_delete_document(
    source_id: str,
    document_source: str,
) -> dict:
    """Delete a document's chunks from Qdrant and Postgres. Returns deleted_chunks count."""
    check_mcp_scope(Scope.WRITE)
    from sqlalchemy import select, delete as sa_delete
    from app.models import Source, ScrapedContent
    from app.services.ingestion.document_ops import DocumentOps

    async with async_session_maker() as db:
        # Resolve source
        stmt = select(Source).where(Source.id == source_id)
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            return {"error": f"Source not found: {source_id}"}

        if not source.collection_name:
            return {"error": "Source has no Qdrant collection — nothing to delete"}

        ops = DocumentOps()

        try:
            # Delete chunks from Qdrant
            deleted_chunks = await ops.delete_document_chunks(
                source.collection_name, document_source
            )

            # Delete ScrapedContent if it exists
            await db.execute(
                sa_delete(ScrapedContent).where(
                    ScrapedContent.source_id == source_id,
                    ScrapedContent.url == document_source,
                )
            )

            # Recalculate counts
            remaining_chunks = await ops.count_source_chunks(
                source.collection_name, source_id
            )
            source.chunk_count = remaining_chunks
            if source.document_count > 0:
                source.document_count = max(0, source.document_count - 1)

            await db.commit()

            logger.info(
                "MCP: Deleted document",
                source_id=source_id,
                document_source=document_source,
                deleted_chunks=deleted_chunks,
            )

            return {
                "status": "deleted",
                "source_id": source_id,
                "document_source": document_source,
                "deleted_chunks": deleted_chunks,
                "remaining_chunks": remaining_chunks,
            }

        except Exception as e:
            return {"error": f"Delete failed: {str(e)}"}


@mcp.tool(
    description="Export chunks from a source with cursor-based pagination. Pass next_offset for subsequent pages.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_export_source_chunks(
    source_id: str,
    limit: int = 500,
    offset: Optional[str] = None,
) -> dict:
    """Export chunks. Returns chunks list, next_offset, has_more."""
    limit = min(limit, 1000)

    async with async_session_maker() as db:
        service = IngestionService(db)
        source = await service.get_source(source_id)
        if not source:
            return {"error": f"Source not found: {source_id}"}

        if not source.collection_name:
            return {"error": f"Source has no collection (not yet indexed): {source_id}"}

        try:
            from app.services.ingestion.qdrant_client import get_qdrant_client

            client = get_qdrant_client()

            # Parse offset for cursor-based pagination
            scroll_offset = None
            if offset:
                scroll_offset = offset

            # Use scroll() for efficient paginated retrieval
            points, next_page_offset = client.scroll(
                collection_name=source.collection_name,
                limit=limit,
                offset=scroll_offset,
                with_payload=True,
                with_vectors=False,
            )

            chunks = []
            for point in points:
                payload = point.payload or {}
                chunks.append({
                    "id": str(point.id),
                    "content": payload.get("content", ""),
                    "source": payload.get("source", ""),
                    "source_id": payload.get("source_id", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "title": payload.get("title", ""),
                    "content_hash": payload.get("content_hash", ""),
                    "scraped_at": payload.get("scraped_at", ""),
                    "embedding_model": payload.get("embedding_model", ""),
                    "metadata": payload.get("metadata", {}),
                })

            next_offset_str = str(next_page_offset) if next_page_offset else None

            logger.info(
                "MCP: Exported knowledge chunks",
                source_id=source_id,
                chunk_count=len(chunks),
                has_more=next_offset_str is not None,
            )

            return _sanitize_for_json({
                "source_id": source_id,
                "source_name": source.name,
                "collection_name": source.collection_name,
                "chunks": chunks,
                "next_offset": next_offset_str,
                "chunk_count": len(chunks),
                "total_expected": source.chunk_count or 0,
                "has_more": next_offset_str is not None,
            })
        except Exception as e:
            logger.error("MCP: Export chunks failed", source_id=source_id, error=str(e))
            return {"error": f"Export failed: {str(e)}"}


@mcp.tool(
    description="Get the current indexing queue — active and queued jobs.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def agentbase_get_indexing_queue() -> dict:
    """Get indexing queue status."""
    async with async_session_maker() as db:
        queue_manager = QueueManager(db)
        return await queue_manager.get_queue_status()
