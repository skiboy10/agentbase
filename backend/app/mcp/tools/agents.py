"""
MCP Tools for Agent Management

CRUD, library bindings, and source bindings for AI agents.
"""

from typing import Annotated, Optional

import structlog
from pydantic import Field

from app.mcp.server import mcp
from app.core.auth import Scope, check_mcp_scope
from app.core.database import async_session_maker
from app.core.events import publish_agent_event
from app.services import AgentService

logger = structlog.get_logger()


def _agent_to_dict(agent, service: AgentService) -> dict:
    """Convert Agent model to dict."""
    info = service.to_info(agent)
    return {
        "id": info.id,
        "agent_id": info.agent_id,
        "name": info.name,
        "description": info.description,
        "system_prompt": info.system_prompt,
        "model_provider": info.model_provider,
        "model_name": info.model_name,
        "temperature": info.temperature,
        "use_rag": info.use_rag,
        "rag_top_k": info.rag_top_k,
        "skills": info.skills,
        "is_public": info.is_public,
        "has_api_key": info.has_api_key,
        "source_ids": info.knowledge_source_ids,
        "library_ids": info.knowledge_base_ids,
        "created_at": info.created_at,
        "updated_at": info.updated_at,
    }


@mcp.tool(
    description="List all agents with pagination. Supports limit/offset pagination (default: limit=50, offset=0).",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_agents(limit: int = 50, offset: int = 0) -> dict:
    """List all agents with pagination.

    Returns:
        dict with keys:
            total (int) - total number of agents,
            count (int) - number of items in this page,
            offset (int) - current offset,
            has_more (bool) - whether more items exist beyond this page,
            next_offset (int|None) - offset for the next page, or None if no more,
            items (list[dict]) - list of agent dicts, each with keys:
                id (str), agent_id (str - slug),
                name (str), description (str|None), system_prompt (str),
                model_provider (str), model_name (str), temperature (float),
                use_rag (bool), rag_top_k (int), skills (list[str]),
                is_public (bool), has_api_key (bool),
                source_ids (list[str]), library_ids (list[str]),
                created_at (str - ISO datetime), updated_at (str - ISO datetime)
        On error: {"error": str}
    """
    async with async_session_maker() as db:
        try:
            service = AgentService(db)
            agents = await service.list_agents()
            total = len(agents)
            page = agents[offset:offset + limit]
            items = [_agent_to_dict(agent, service) for agent in page]
            return {
                "total": total,
                "count": len(items),
                "offset": offset,
                "has_more": offset + len(items) < total,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "items": items,
            }
        except Exception as e:
            return {"error": f"Failed to list agents: {str(e)}"}


@mcp.tool(
    description="Get an agent's full configuration by ID.",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_get_agent(agent_id: str) -> dict:
    """Get agent details including configuration, bindings, and metadata.

    Returns:
        dict with keys:
            id (str), agent_id (str - slug),
            name (str), description (str|None), system_prompt (str),
            model_provider (str), model_name (str), temperature (float),
            use_rag (bool), rag_top_k (int), skills (list[str]),
            is_public (bool), has_api_key (bool),
            source_ids (list[str]), library_ids (list[str]),
            created_at (str - ISO datetime), updated_at (str - ISO datetime)
        On error: {"error": str}
    """
    async with async_session_maker() as db:
        service = AgentService(db)
        agent = await service.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}
        return _agent_to_dict(agent, service)


@mcp.tool(
    description=(
        "Create an agent. Requires name, system_prompt, model_provider, and model_name. "
        "After creation, use agentbase_bind_knowledge_base to give it library access for RAG."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_create_agent(
    name: Annotated[str, Field(
        min_length=1, max_length=255,
        description="Display name, e.g. 'ACME Support Assistant'",
    )],
    system_prompt: Annotated[str, Field(
        min_length=1, description="System prompt that defines the agent's behavior",
    )],
    model_provider: Annotated[str, Field(
        min_length=1, max_length=50,
        description="LLM provider, e.g. 'ollama', 'openai', 'anthropic'",
    )],
    model_name: Annotated[str, Field(
        min_length=1, max_length=100,
        description="Model identifier as known to the provider",
    )],
    description: Optional[str] = None,
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.7,
    use_rag: bool = True,
    rag_top_k: Annotated[int, Field(
        ge=1, le=50, description="Chunks retrieved per RAG query",
    )] = 5,
    is_public: bool = False,
    knowledge_source_ids: Optional[list[str]] = None,
) -> dict:
    """Create a new agent."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = AgentService(db)
        try:
            agent = await service.create_agent(
                name=name,
                description=description,
                system_prompt=system_prompt,
                model_provider=model_provider,
                model_name=model_name,
                temperature=temperature,
                use_rag=use_rag,
                rag_top_k=rag_top_k,
                skills=[],
                is_public=is_public,
                knowledge_source_ids=knowledge_source_ids,
            )
            result = _agent_to_dict(agent, service)
            await publish_agent_event("created", agent.id, {"name": name}, source="mcp")
            return result
        except ValueError as e:
            return {"error": str(e)}


@mcp.tool(
    description="Update an agent. Pass only the fields you want to change.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_update_agent(
    agent_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    system_prompt: Optional[str] = None,
    model_provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    use_rag: Optional[bool] = None,
    rag_top_k: Optional[int] = None,
    is_public: Optional[bool] = None,
    knowledge_source_ids: Optional[list[str]] = None,
) -> dict:
    """Update an agent."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = AgentService(db)
        try:
            agent = await service.update_agent(
                agent_id=agent_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                model_provider=model_provider,
                model_name=model_name,
                temperature=temperature,
                use_rag=use_rag,
                rag_top_k=rag_top_k,
                is_public=is_public,
                knowledge_source_ids=knowledge_source_ids,
            )
        except ValueError as e:
            # Model preflight failures (#176) — return as tool error
            return {"error": str(e)}
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}
        result = _agent_to_dict(agent, service)
        await publish_agent_event("updated", agent_id, {"name": agent.name}, source="mcp")
        return result


@mcp.tool(
    description="Delete an agent. Irreversible.",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_delete_agent(agent_id: str) -> dict:
    """Delete an agent."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = AgentService(db)
        deleted = await service.delete_agent(agent_id)
        if not deleted:
            return {"error": f"Agent not found: {agent_id}"}
        await publish_agent_event("deleted", agent_id, source="mcp")
        return {"status": "deleted", "id": agent_id}


@mcp.tool(
    description=(
        "Bind individual sources to an agent for RAG. "
        "Prefer agentbase_bind_knowledge_base (library-level) over this for most use cases."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_bind_knowledge_to_agent(
    agent_id: str,
    knowledge_source_ids: list[str],
) -> dict:
    """Bind knowledge sources to an agent."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = AgentService(db)
        agent = await service.update_agent(
            agent_id=agent_id,
            knowledge_source_ids=knowledge_source_ids,
        )
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}
        return _agent_to_dict(agent, service)


@mcp.tool(
    description=(
        "Bind a library to an agent (preferred over per-source binding). "
        "The agent searches all sources in the library during RAG."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_bind_knowledge_base(agent_id: str, library_id: str) -> dict:
    """Bind a library to an agent. Returns 'bound' or 'already_bound'."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = AgentService(db)
        binding = await service.bind_knowledge_base(agent_id, library_id)
        if binding is None:
            agent = await service.get_agent(agent_id)
            if not agent:
                return {"error": f"Agent not found: {agent_id}"}
            return {"status": "already_bound", "agent_id": agent_id, "library_id": library_id}
        return {"status": "bound", "agent_id": agent_id, "library_id": library_id}


@mcp.tool(
    description="Unbind a library from an agent.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_unbind_knowledge_base(agent_id: str, library_id: str) -> dict:
    """Remove a library binding from an agent."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        service = AgentService(db)
        removed = await service.unbind_knowledge_base(agent_id, library_id)
        if not removed:
            return {"error": f"Library binding not found for agent {agent_id} / library {library_id}"}
        return {"status": "unbound", "agent_id": agent_id, "library_id": library_id}


@mcp.tool(
    description="List all libraries bound to an agent with pagination. Supports limit/offset pagination (default: limit=50, offset=0).",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_agent_knowledge_bases(agent_id: str, limit: int = 50, offset: int = 0) -> dict:
    """Return all libraries bound to the specified agent with pagination.

    Returns:
        dict with keys:
            total (int) - total number of bound libraries,
            count (int) - number of items in this page,
            offset (int) - current offset,
            has_more (bool) - whether more items exist beyond this page,
            next_offset (int|None) - offset for the next page, or None if no more,
            items (list[dict]) - list of library dicts, each with keys:
                id (str), name (str), description (str|None),
                status (str), collection_name (str|None),
                source_count (int), document_count (int), chunk_count (int)
        On error: {"error": str}
    """
    async with async_session_maker() as db:
        try:
            service = AgentService(db)
            agent = await service.get_agent(agent_id)
            if not agent:
                return {"error": f"Agent not found: {agent_id}"}
            kbs = await service.get_agent_knowledge_bases(agent_id)
            total = len(kbs)
            page = kbs[offset:offset + limit]
            items = [
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "status": kb.status,
                    "collection_name": kb.collection_name,
                    "source_count": kb.source_count,
                    "document_count": kb.document_count,
                    "chunk_count": kb.chunk_count,
                }
                for kb in page
            ]
            return {
                "total": total,
                "count": len(items),
                "offset": offset,
                "has_more": offset + len(items) < total,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "items": items,
            }
        except Exception as e:
            return {"error": f"Failed to list agent knowledge bases: {str(e)}"}
