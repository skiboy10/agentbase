"""
Agent query endpoint.

POST /api/agents/{agent_id}/query

Stateless RAG-grounded Q&A: takes a natural language question, retrieves
relevant chunks from the agent's bound knowledge sources, calls the agent's
LLM with context, and returns a synthesized answer with source attribution.

Auth policy mirrors /invoke — external requests require API key and a public
agent; internal (LAN) requests pass through.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import is_external_request
from app.core.database import get_db
from app.services.agent_service import AgentService
from app.services.agent_query import AgentQueryService
from .schemas import AgentQueryRequest, AgentQueryResponse, AgentQuerySourceItem

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/agents/{agent_id}/query", response_model=AgentQueryResponse)
@limiter.limit("30/minute")
async def query_agent(
    agent_id: str,
    data: AgentQueryRequest,
    request: Request,
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a query to an agent and get a synthesized answer with sources.

    The agent searches its bound knowledge base, builds context, and calls
    its configured LLM to produce a grounded answer.

    External requests (via tunnel) require X-API-Key and agent must be public.
    Internal (LAN) requests pass through without auth.
    """
    # Auth enforcement — same as /invoke
    agent_service = AgentService(db)
    agent = await agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if is_external_request(request):
        if not agent.is_public:
            raise HTTPException(
                status_code=403,
                detail="Agent is not available for external access",
            )
        if not x_api_key:
            raise HTTPException(status_code=401, detail="API key required")
        validated_agent = await agent_service.validate_api_key(x_api_key)
        if not validated_agent or validated_agent.id != agent_id:
            raise HTTPException(status_code=401, detail="Invalid API key")

    # Execute query
    query_service = AgentQueryService(db)
    try:
        result = await query_service.query(
            agent_id=agent_id,
            query=data.query,
            filters=data.filters,
            session_id=data.session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    return AgentQueryResponse(
        answer=result["answer"],
        sources=[
            AgentQuerySourceItem(**s)
            for s in result["sources"]
        ],
        query=result["query"],
        model=result["model"],
        agent_id=result["agent_id"],
    )
