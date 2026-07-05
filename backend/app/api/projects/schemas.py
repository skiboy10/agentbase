"""
Pydantic schemas for project API endpoints.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    """Project creation request."""
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Project update request."""
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    knowledge_provider: Optional[str] = None
    knowledge_model: Optional[str] = None


class ProjectResponse(BaseModel):
    """Project response model."""
    id: str
    name: str
    description: Optional[str]
    instructions: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    knowledge_provider: Optional[str] = None
    knowledge_model: Optional[str] = None

    class Config:
        from_attributes = True


class AssignSourcesRequest(BaseModel):
    """Request to assign knowledge sources to a project."""
    source_ids: list[str]


class UnassignSourcesRequest(BaseModel):
    """Request to unassign knowledge sources from a project."""
    source_ids: list[str]


class SourceAssignment(BaseModel):
    """Source assignment info for a project."""
    id: str
    source_id: str
    source_name: str
    source_type: str
    status: str
    document_count: int
    chunk_count: int
    is_global: bool
    assigned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Backward-compatible alias
KnowledgeSourceAssignment = SourceAssignment


