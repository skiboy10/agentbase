"""
Agent CRUD endpoints.

Handles list, get, create, update, delete operations.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services import AgentService
from .schemas import AgentCreate, AgentUpdate, AgentResponse
from .helpers import agent_to_response

router = APIRouter()


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all agents."""
    service = AgentService(db)
    agents = await service.list_agents()
    return [agent_to_response(agent, service) for agent in agents]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a specific agent by ID."""
    service = AgentService(db)
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_to_response(agent, service)


@router.post("/agents", response_model=AgentResponse, status_code=201)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Create a new agent."""
    service = AgentService(db)
    try:
        agent = await service.create_agent(
            name=data.name,
            description=data.description,
            system_prompt=data.system_prompt,
            model_provider=data.model_provider,
            model_name=data.model_name,
            temperature=data.temperature,
            use_rag=data.use_rag,
            rag_top_k=data.rag_top_k,
            skills=data.skills,
            is_public=data.is_public,
            knowledge_source_ids=data.source_ids,
        )
        return agent_to_response(agent, service)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update an existing agent."""
    service = AgentService(db)
    try:
        agent = await service.update_agent(
            agent_id=agent_id,
            name=data.name,
            description=data.description,
            system_prompt=data.system_prompt,
            model_provider=data.model_provider,
            model_name=data.model_name,
            temperature=data.temperature,
            use_rag=data.use_rag,
            rag_top_k=data.rag_top_k,
            skills=data.skills,
            is_public=data.is_public,
            knowledge_source_ids=data.source_ids,
        )
    except ValueError as e:
        # Model preflight failures surface as actionable 400s
        raise HTTPException(status_code=400, detail=str(e))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_to_response(agent, service)


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Delete an agent."""
    service = AgentService(db)
    deleted = await service.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "id": agent_id}
