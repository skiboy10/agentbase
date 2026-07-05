"""
Prompts API endpoints.

This module provides API endpoints for managing system prompts
scoped to projects or globally.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services import PromptService

router = APIRouter()


# ==================== Pydantic Schemas ====================

class PromptCreate(BaseModel):
    """Prompt creation request."""
    name: str
    task_type: str
    system_prompt: str
    project_id: Optional[str] = None
    description: Optional[str] = None
    rag_context_template: Optional[str] = None
    use_rag: bool = True
    is_default: bool = False


class PromptUpdate(BaseModel):
    """Prompt update request."""
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    rag_context_template: Optional[str] = None
    use_rag: Optional[bool] = None
    is_default: Optional[bool] = None
    increment_version: bool = False


class PromptDuplicate(BaseModel):
    """Prompt duplication request."""
    new_name: str
    target_project_id: Optional[str] = None


class PromptResponse(BaseModel):
    """Prompt response."""
    id: str
    project_id: Optional[str]
    name: str
    description: Optional[str]
    task_type: str
    system_prompt: str
    rag_context_template: Optional[str]
    use_rag: bool
    is_default: bool
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskTypesResponse(BaseModel):
    """List of task types."""
    task_types: list[str]


# ==================== Endpoints ====================

@router.get("/prompts", response_model=list[PromptResponse])
async def list_prompts(
    project_id: Optional[str] = None,
    task_type: Optional[str] = None,
    include_global: bool = True,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    List prompts, optionally filtered by project and/or task type.

    - **project_id**: Filter to specific project (omit for global only)
    - **task_type**: Filter to specific task type (e.g., knowledge)
    - **include_global**: Include global prompts when project_id is specified
    """
    service = PromptService(db)
    prompts = await service.list_prompts(project_id, task_type, include_global)
    return prompts


@router.get("/prompts/task-types", response_model=TaskTypesResponse)
async def get_task_types(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get list of available task types."""
    service = PromptService(db)
    task_types = await service.get_task_types(project_id)
    return TaskTypesResponse(task_types=task_types)


@router.get("/prompts/default/{task_type}", response_model=PromptResponse)
async def get_default_prompt(
    task_type: str,
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    Get the default prompt for a task type.

    Resolution order:
    1. Project-specific default (if project_id provided)
    2. Global default
    """
    service = PromptService(db)
    prompt = await service.get_default_prompt(task_type, project_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"No default prompt found for task type: {task_type}")
    return prompt


@router.get("/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a specific prompt by ID."""
    service = PromptService(db)
    prompt = await service.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post("/prompts", response_model=PromptResponse, status_code=201)
async def create_prompt(
    data: PromptCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Create a new prompt."""
    service = PromptService(db)
    try:
        prompt = await service.create_prompt(
            name=data.name,
            task_type=data.task_type,
            system_prompt=data.system_prompt,
            project_id=data.project_id,
            description=data.description,
            rag_context_template=data.rag_context_template,
            use_rag=data.use_rag,
            is_default=data.is_default
        )
        return prompt
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/prompts/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: str,
    data: PromptUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update an existing prompt."""
    service = PromptService(db)
    prompt = await service.update_prompt(
        prompt_id=prompt_id,
        name=data.name,
        description=data.description,
        system_prompt=data.system_prompt,
        rag_context_template=data.rag_context_template,
        use_rag=data.use_rag,
        is_default=data.is_default,
        increment_version=data.increment_version
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Delete a prompt."""
    service = PromptService(db)
    try:
        deleted = await service.delete_prompt(prompt_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"status": "deleted", "id": prompt_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/prompts/{prompt_id}/duplicate", response_model=PromptResponse, status_code=201)
async def duplicate_prompt(
    prompt_id: str,
    data: PromptDuplicate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Duplicate a prompt, optionally to a different project.

    Useful for creating project-specific versions from global templates.
    """
    service = PromptService(db)
    prompt = await service.duplicate_prompt(
        prompt_id=prompt_id,
        new_name=data.new_name,
        target_project_id=data.target_project_id
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Source prompt not found")
    return prompt
