"""
Agent API key management endpoints.

Handles API key generation.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services import AgentService
from .schemas import ApiKeyResponse

router = APIRouter()


@router.post("/agents/{agent_id}/api-key", response_model=ApiKeyResponse)
async def generate_api_key(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Generate a new API key for an agent."""
    service = AgentService(db)
    try:
        api_key = await service.set_api_key(agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate API key: {e}")
    if not api_key:
        raise HTTPException(status_code=404, detail="Agent not found")
    return ApiKeyResponse(
        api_key=api_key,
        message="Store this key securely - it won't be shown again"
    )
