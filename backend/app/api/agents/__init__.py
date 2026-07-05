"""
Agents API router package.

Aggregates all agent-related endpoints from sub-modules.
"""

from fastapi import APIRouter

from .crud import router as crud_router
from .management import router as management_router
from .api_keys import router as api_keys_router
from .query import router as query_router
from .libraries import router as libraries_router

from .schemas import (
    AgentCreate,
    AgentUpdate,
    AgentDuplicate,
    AgentResponse,
    ApiKeyResponse,
    AgentQueryRequest,
    AgentQueryResponse,
    AgentQuerySourceItem,
)

from .helpers import agent_to_response

router = APIRouter()

router.include_router(management_router, tags=["agents"])
router.include_router(crud_router, tags=["agents"])
router.include_router(api_keys_router, tags=["agents"])
router.include_router(query_router, tags=["agents"])
router.include_router(libraries_router, tags=["agents"])


__all__ = [
    "router",
    "AgentCreate", "AgentUpdate", "AgentDuplicate",
    "AgentResponse", "ApiKeyResponse",
    "AgentQueryRequest", "AgentQueryResponse", "AgentQuerySourceItem",
    "agent_to_response",
]
