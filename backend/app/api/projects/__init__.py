"""
Projects API package.

Provides endpoints for project management including:
- CRUD operations
- Source assignments
"""
from fastapi import APIRouter

from .crud import router as crud_router
from .knowledge import router as knowledge_router

router = APIRouter()

router.include_router(crud_router, tags=["projects"])
router.include_router(knowledge_router, tags=["projects"])

from .schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    AssignSourcesRequest,
    UnassignSourcesRequest,
    SourceAssignment,
    KnowledgeSourceAssignment,
)

__all__ = [
    "router",
    "ProjectCreate", "ProjectUpdate", "ProjectResponse",
    "AssignSourcesRequest", "UnassignSourcesRequest",
    "SourceAssignment", "KnowledgeSourceAssignment",
]
