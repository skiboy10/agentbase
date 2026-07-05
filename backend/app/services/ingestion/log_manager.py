"""
Indexing log management.

Handles operations for indexing logs: retrieval, summary, and cleanup.
"""
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source, IndexingLog

from .types import IndexingStatus, IndexingLogEntry, IndexingLogSummary


class LogManager:
    """
    Manages indexing logs and status.

    Handles:
    - Indexing status retrieval
    - Log retrieval with filtering
    - Summary statistics
    - Log cleanup
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_source(self, source_id: str) -> Optional[Source]:
        """Get a specific knowledge source."""
        stmt = select(Source).where(Source.id == source_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_indexing_status(self, source_id: str) -> IndexingStatus:
        """Get the current indexing status of a knowledge source."""
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        return IndexingStatus(
            source_id=source.id,
            status=source.status,
            progress=source.progress,
            progress_total=source.progress_total,
            progress_message=source.progress_message,
            document_count=source.document_count,
            chunk_count=source.chunk_count,
            error_message=source.error_message,
        )

    async def get_indexing_logs(
        self,
        source_id: str,
        status_filter: Optional[str] = None,
        limit: int = 500
    ) -> IndexingLogSummary:
        """Get indexing logs for a knowledge source with summary stats."""
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        stmt = select(IndexingLog).where(IndexingLog.source_id == source_id)
        if status_filter:
            stmt = stmt.where(IndexingLog.status == status_filter)
        stmt = stmt.order_by(IndexingLog.updated_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        logs = result.scalars().all()

        all_logs_stmt = select(IndexingLog).where(IndexingLog.source_id == source_id)
        all_logs_result = await self.db.execute(all_logs_stmt)
        all_logs = all_logs_result.scalars().all()

        return IndexingLogSummary(
            logs=[
                IndexingLogEntry(
                    id=log.id,
                    source_id=log.source_id,
                    url=log.url,
                    status=log.status,
                    error_message=log.error_message,
                    scrape_duration_ms=log.scrape_duration_ms,
                    embed_duration_ms=log.embed_duration_ms,
                    content_length=log.content_length,
                    chunk_count=log.chunk_count,
                    created_at=log.created_at,
                    updated_at=log.updated_at,
                )
                for log in logs
            ],
            total=len(all_logs),
            done=sum(1 for log in all_logs if log.status == "done"),
            failed=sum(1 for log in all_logs if log.status == "failed"),
            skipped=sum(1 for log in all_logs if log.status == "skipped"),
            pending=sum(1 for log in all_logs if log.status == "pending"),
            in_progress=sum(1 for log in all_logs if log.status in ("scraping", "scraped", "embedding")),
        )

    async def clear_indexing_logs(self, source_id: str) -> bool:
        """Clear all indexing logs for a knowledge source."""
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Source not found")

        delete_stmt = delete(IndexingLog).where(IndexingLog.source_id == source_id)
        await self.db.execute(delete_stmt)
        return True
