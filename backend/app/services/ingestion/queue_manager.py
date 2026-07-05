"""
Queue manager for throttling indexing jobs.

Provides concurrency control to prevent overwhelming the embedding pipeline
when multiple knowledge sources are uploaded simultaneously.
"""

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source
from app.core.config import get_settings


class QueueManager:
    """Manages indexing job queue with concurrency limits."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def get_active_count(self) -> int:
        """Count sources currently indexing."""
        stmt = select(func.count()).select_from(Source).where(
            Source.status == "indexing"
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def can_start_indexing(self) -> bool:
        """Check if under concurrency limit."""
        active = await self.get_active_count()
        return active < self.settings.max_concurrent_indexing

    async def get_queue_position(self, source_id: str) -> int:
        """Get queue position (0 if not queued)."""
        stmt = select(Source).where(Source.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source or source.status != "queued":
            return 0

        # Count queued sources created before this one
        count_stmt = (
            select(func.count())
            .select_from(Source)
            .where(
                Source.status == "queued",
                Source.created_at < source.created_at,
            )
        )
        result = await self.db.execute(count_stmt)
        return (result.scalar() or 0) + 1

    async def get_next_queued(self) -> Optional[str]:
        """Get oldest queued source ID."""
        stmt = (
            select(Source.id)
            .where(Source.status == "queued")
            .order_by(Source.created_at.asc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_queue_status(self) -> dict:
        """Get full queue status for monitoring."""
        settings = get_settings()

        active_stmt = select(Source).where(
            Source.status == "indexing"
        )
        queued_stmt = (
            select(Source)
            .where(Source.status == "queued")
            .order_by(Source.created_at.asc())
        )

        active_result = await self.db.execute(active_stmt)
        queued_result = await self.db.execute(queued_stmt)

        active_sources = active_result.scalars().all()
        queued_sources = queued_result.scalars().all()

        sources = []
        for s in active_sources:
            sources.append(
                {
                    "source_id": s.id,
                    "name": s.name,
                    "status": "indexing",
                    "progress": s.progress,
                    "progress_total": s.progress_total,
                    "progress_message": s.progress_message,
                }
            )
        for i, s in enumerate(queued_sources, 1):
            sources.append(
                {
                    "source_id": s.id,
                    "name": s.name,
                    "status": "queued",
                    "queue_position": i,
                }
            )

        return {
            "active_jobs": len(active_sources),
            "queued_jobs": len(queued_sources),
            "max_concurrent": settings.max_concurrent_indexing,
            "sources": sources,
        }
