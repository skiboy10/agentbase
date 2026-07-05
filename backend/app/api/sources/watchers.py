"""
Watcher management endpoints for directory source file watching.

Provides status, start/stop, force-sync, and event log operations for the
WatcherManager singleton.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import Scope, require_scope
from app.models import APIKey, WatcherEvent
from app.services.ingestion.watcher import watcher_manager

router = APIRouter(prefix="/watchers", tags=["watchers"])


@router.get("/status")
async def get_watcher_statuses(
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get status of all active file watchers."""
    return {
        "watchers": watcher_manager.get_all_statuses(),
    }


@router.get("/status/{source_id}")
async def get_watcher_status(
    source_id: str,
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get status of a specific source's file watcher."""
    status = watcher_manager.get_status(source_id)
    if not status:
        raise HTTPException(status_code=404, detail="No active watcher for this source")
    return status


@router.post("/{source_id}/start")
async def start_watcher(
    source_id: str,
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Start the file watcher for a directory source."""
    try:
        await watcher_manager.start_watcher(source_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "source_id": source_id}


@router.post("/{source_id}/stop")
async def stop_watcher(
    source_id: str,
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Stop the file watcher for a directory source."""
    try:
        await watcher_manager.stop_watcher(source_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "stopped", "source_id": source_id}


@router.post("/{source_id}/sync")
async def force_sync(
    source_id: str,
    allow_mass_delete: bool = Query(
        default=False,
        description="Confirm an intended bulk removal. By default a sync that would "
        "delete >=90% of the indexed set is refused (broken-mount safety guard).",
    ),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Force a full directory sync for a source (scan for changes now)."""
    try:
        result = await watcher_manager.force_sync(source_id, db, allow_mass_delete=allow_mass_delete)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/{source_id}/events")
async def list_watcher_events(
    source_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    before: Optional[str] = Query(default=None, description="ISO timestamp cursor for pagination"),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    Get watcher event log for a source, newest first.

    Paginate using the `next_before` cursor from the previous response.
    """
    stmt = (
        select(WatcherEvent)
        .where(WatcherEvent.source_id == source_id)
        .order_by(desc(WatcherEvent.timestamp))
        .limit(limit + 1)
    )
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
            stmt = stmt.where(WatcherEvent.timestamp < before_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'before' timestamp format; use ISO 8601")

    result = await db.execute(stmt)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    events = rows[:limit]

    next_before = events[-1].timestamp.isoformat() if has_more and events else None

    return {
        "events": [
            {
                "id": e.id,
                "source_id": e.source_id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "file_path": e.file_path,
                "severity": e.severity,
                "message": e.message,
            }
            for e in events
        ],
        "next_before": next_before,
    }
