"""
Agent Library binding endpoints.

Manages Library-level bindings (AgentKnowledgeBase) for agents.
Library bindings query the Library's Qdrant collection directly, which is faster
than the legacy per-source filtering via AgentKnowledgeSource.

These endpoints are the preferred path. Legacy /knowledge-sources
bindings remain for backward compatibility.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services import AgentService

router = APIRouter()


def _library_to_dict(kb) -> dict:
    """Return a lightweight Library summary."""
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "status": kb.status,
        "collection_name": kb.collection_name,
        "source_count": kb.source_count,
        "document_count": kb.document_count,
        "chunk_count": kb.chunk_count,
    }


@router.post("/agents/{agent_id}/libraries/{library_id}", status_code=201)
async def bind_library(
    agent_id: str,
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Bind a Library to an agent.

    Returns 201 on successful bind, 200 if already bound (idempotent),
    404 if agent or Library not found.
    """
    service = AgentService(db)

    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from sqlalchemy import select
    from app.models import Library as KBModel
    kb_stmt = select(KBModel).where(KBModel.id == library_id)
    kb_result = await db.execute(kb_stmt)
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Library not found")

    binding = await service.bind_knowledge_base(agent_id, library_id)

    if binding is None:
        # Already bound — idempotent
        return {"status": "already_bound", "agent_id": agent_id, "library": _library_to_dict(kb)}

    return {"status": "bound", "agent_id": agent_id, "library": _library_to_dict(kb)}


@router.delete("/agents/{agent_id}/libraries/{library_id}")
async def unbind_library(
    agent_id: str,
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Remove a Library binding from an agent."""
    service = AgentService(db)

    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    removed = await service.unbind_knowledge_base(agent_id, library_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Library binding not found",
        )

    return {"status": "unbound", "agent_id": agent_id, "library_id": library_id}


@router.get("/agents/{agent_id}/libraries")
async def list_agent_libraries(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all Libraries bound to an agent."""
    service = AgentService(db)

    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    kbs = await service.get_agent_knowledge_bases(agent_id)
    return [_library_to_dict(kb) for kb in kbs]
