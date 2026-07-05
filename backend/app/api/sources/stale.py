"""
Stale sources endpoint.

Lists sources that are approaching or past their staleness threshold.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import Scope, require_scope
from app.models import APIKey
from app.services.freshness_service import list_stale_sources

router = APIRouter()


@router.get("/stale")
async def get_stale_sources(
    library_id: Optional[str] = None,
    freshness_policy: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List sources that are stale or approaching staleness.

    Filters to sources with freshness_policy of 'automatic' or 'manual'
    that have a stale_after_days threshold configured.

    Optional query params:
    - library_id: filter to sources in a specific library
    - freshness_policy: filter to 'automatic' or 'manual'
    """
    return await list_stale_sources(db, library_id=library_id, policy=freshness_policy)
