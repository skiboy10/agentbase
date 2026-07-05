"""
Freshness lifecycle service.

Computes freshness status for sources and identifies stale sources
needing refresh or manual review.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Source

logger = structlog.get_logger()

# Freshness status constants
STATUS_CURRENT = "current"
STATUS_AGING = "aging"
STATUS_STALE = "stale"

# Aging threshold: source is "aging" when it has consumed 80% of its stale window
AGING_THRESHOLD_RATIO = 0.8


def get_freshness_status(source: Source) -> str:
    """Compute freshness status for a single source.

    Returns "current", "aging", or "stale" based on last_indexed vs stale_after_days.
    Sources with freshness_policy="none" or no stale_after_days always return "current".
    """
    policy = source.freshness_policy or "none"
    if policy == "none" or not source.stale_after_days:
        return STATUS_CURRENT

    if not source.last_indexed:
        # Never indexed — treat as stale for automatic/manual policies
        return STATUS_STALE

    now = datetime.utcnow()
    age = now - source.last_indexed
    threshold = timedelta(days=source.stale_after_days)
    aging_threshold = threshold * AGING_THRESHOLD_RATIO

    if age >= threshold:
        return STATUS_STALE
    elif age >= aging_threshold:
        return STATUS_AGING
    else:
        return STATUS_CURRENT


def compute_next_refresh_at(source: Source) -> Optional[datetime]:
    """Compute next_refresh_at based on last_indexed + refresh_interval_days.

    Only applicable for automatic policy sources with a refresh interval.
    """
    if (source.freshness_policy or "none") != "automatic":
        return None
    if not source.refresh_interval_days or not source.last_indexed:
        return None
    return source.last_indexed + timedelta(days=source.refresh_interval_days)


async def list_stale_sources(
    db: AsyncSession,
    library_id: Optional[str] = None,
    policy: Optional[str] = None,
) -> list[dict]:
    """List sources that are stale or approaching staleness.

    Returns a list of dicts with source info and computed freshness_status.
    """
    from app.models import LibrarySource

    stmt = select(Source).where(
        Source.freshness_policy.in_(["automatic", "manual"]),
        Source.stale_after_days.isnot(None),
    )

    if library_id:
        stmt = stmt.join(LibrarySource, LibrarySource.source_id == Source.id).where(
            LibrarySource.library_id == library_id
        )
    if policy:
        stmt = stmt.where(Source.freshness_policy == policy)

    stmt = stmt.order_by(Source.last_indexed.asc().nullsfirst())
    result = await db.execute(stmt)
    sources = result.scalars().all()

    stale_list = []
    for source in sources:
        status = get_freshness_status(source)
        if status in (STATUS_STALE, STATUS_AGING):
            stale_list.append({
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type,
                "freshness_policy": source.freshness_policy,
                "freshness_status": status,
                "stale_after_days": source.stale_after_days,
                "refresh_interval_days": source.refresh_interval_days,
                "last_indexed": source.last_indexed.isoformat() if source.last_indexed else None,
                "next_refresh_at": source.next_refresh_at.isoformat() if source.next_refresh_at else None,
            })

    return stale_list
