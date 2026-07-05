"""
Project CRUD operations.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import Project, APIKey, ModelAssignment
from .schemas import ProjectCreate, ProjectUpdate, ProjectResponse

router = APIRouter()


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all projects."""
    stmt = select(Project).order_by(Project.updated_at.desc())
    result = await db.execute(stmt)
    projects = result.scalars().all()

    return [
        ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            instructions=project.instructions,
            created_at=project.created_at,
            updated_at=project.updated_at,
            knowledge_provider=project.knowledge_provider,
            knowledge_model=project.knowledge_model,
        )
        for project in projects
    ]


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    project: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Create a new project."""
    db_project = Project(
        name=project.name,
        description=project.description,
    )
    db.add(db_project)
    await db.flush()
    await db.refresh(db_project)

    return ProjectResponse(
        id=db_project.id,
        name=db_project.name,
        description=db_project.description,
        created_at=db_project.created_at,
        updated_at=db_project.updated_at,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a specific project by ID."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        instructions=project.instructions,
        created_at=project.created_at,
        updated_at=project.updated_at,
        knowledge_provider=project.knowledge_provider,
        knowledge_model=project.knowledge_model,
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update a project."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update only provided fields
    update_data = project_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        instructions=project.instructions,
        created_at=project.created_at,
        updated_at=project.updated_at,
        knowledge_provider=project.knowledge_provider,
        knowledge_model=project.knowledge_model,
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Delete a project and all associated data.

    Agents are not affected — they no longer reference projects.
    """
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)
    return None


class DefaultModelRequest(BaseModel):
    """Request to set a project's default model."""
    task_type: str  # "knowledge" or "embedding"
    provider: str
    model: str


@router.put("/{project_id}/default-model")
async def set_project_default_model(
    project_id: str,
    request: DefaultModelRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Set a project-level default model assignment.

    Creates or updates a ModelAssignment scoped to this project.
    This overrides the global default for agents in this project.
    """
    if request.task_type not in ["knowledge", "embedding"]:
        raise HTTPException(status_code=400, detail="task_type must be 'knowledge' or 'embedding'")

    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if a project-scoped assignment already exists for this task_type
    existing_stmt = select(ModelAssignment).where(
        ModelAssignment.project_id == project_id,
        ModelAssignment.task_type == request.task_type,
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.provider = request.provider
        existing.model = request.model
    else:
        new_assignment = ModelAssignment(
            project_id=project_id,
            task_type=request.task_type,
            provider=request.provider,
            model=request.model,
        )
        db.add(new_assignment)

    await db.flush()

    return {
        "status": "assigned",
        "project_id": project_id,
        "task_type": request.task_type,
        "provider": request.provider,
        "model": request.model,
    }
