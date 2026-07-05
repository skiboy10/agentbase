"""
Agent management endpoints.

Handles duplicate operations.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services import AgentService
from .schemas import AgentDuplicate, AgentResponse
from .dependencies import is_external_request
from .helpers import agent_to_response

router = APIRouter()


@router.post("/agents/{agent_id}/duplicate", response_model=AgentResponse, status_code=201)
async def duplicate_agent(
    agent_id: str,
    data: AgentDuplicate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Duplicate an agent. Blocked for external requests."""
    if is_external_request(request):
        raise HTTPException(
            status_code=403,
            detail="Agent management is not available externally",
        )
    service = AgentService(db)
    agent = await service.duplicate_agent(
        agent_id=agent_id,
        new_name=data.new_name,
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Source agent not found")
    return agent_to_response(agent, service)
