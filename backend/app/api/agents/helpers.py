"""
Helper functions for Agent API endpoints.
"""

from app.services import AgentService


def agent_to_response(agent, service: AgentService) -> dict:
    """Convert Agent model to response dict (full, for internal use)."""
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
        "available_in_chat": getattr(agent, 'available_in_chat', False),
        "extension_id": getattr(agent, 'extension_id', None),
        "has_api_key": info.has_api_key,
        "source_ids": info.knowledge_source_ids,
        "library_ids": info.knowledge_base_ids,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def agent_to_public_response(agent, service: AgentService) -> dict:
    """Convert Agent model to response dict with sensitive fields redacted."""
    response = agent_to_response(agent, service)
    response["system_prompt"] = "[redacted]"
    response["source_ids"] = []
    return response
