"""
Source assignment endpoints for projects.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import Project, Source, ProjectSource, APIKey
from .schemas import AssignSourcesRequest, UnassignSourcesRequest, SourceAssignment

router = APIRouter()


@router.get("/{project_id}/knowledge-sources", response_model=list[SourceAssignment])
async def list_project_knowledge_sources(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    List knowledge sources available for a project.

    Returns both:
    - Project-specific sources (is_global=False)
    - Assigned global sources (is_global=True)
    """
    # Verify project exists
    proj_stmt = select(Project).where(Project.id == project_id)
    proj_result = await db.execute(proj_stmt)
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    assignments = []

    # 1. Get project-specific sources
    project_sources_stmt = select(Source).where(
        Source.project_id == project_id
    ).order_by(Source.created_at.desc())
    project_result = await db.execute(project_sources_stmt)
    project_sources = project_result.scalars().all()

    for source in project_sources:
        assignments.append(SourceAssignment(
            id=source.id,
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            status=source.status,
            document_count=source.document_count,
            chunk_count=source.chunk_count,
            is_global=False,
            assigned_at=None,
        ))

    # 2. Get assigned global sources via junction table
    assigned_stmt = (
        select(Source, ProjectSource.assigned_at)
        .join(ProjectSource, Source.id == ProjectSource.source_id)
        .where(ProjectSource.project_id == project_id)
        .order_by(ProjectSource.assigned_at.desc())
    )
    assigned_result = await db.execute(assigned_stmt)
    assigned_rows = assigned_result.all()

    for source, assigned_at in assigned_rows:
        assignments.append(SourceAssignment(
            id=source.id,
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            status=source.status,
            document_count=source.document_count,
            chunk_count=source.chunk_count,
            is_global=True,
            assigned_at=assigned_at,
        ))

    return assignments


@router.post("/{project_id}/knowledge-sources")
async def assign_knowledge_sources(
    project_id: str,
    request: AssignSourcesRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Assign global knowledge sources to a project.

    Only global sources (project_id IS NULL) can be assigned.
    Project-specific sources are automatically part of their project.
    """
    # Verify project exists
    proj_stmt = select(Project).where(Project.id == project_id)
    proj_result = await db.execute(proj_stmt)
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    assigned_count = 0

    for source_id in request.source_ids:
        # Verify source exists and is global
        source_stmt = select(Source).where(
            Source.id == source_id,
            Source.project_id.is_(None)
        )
        source_result = await db.execute(source_stmt)
        source = source_result.scalar_one_or_none()

        if not source:
            continue  # Skip non-existent or non-global sources

        # Check if already assigned
        existing_stmt = select(ProjectSource).where(
            ProjectSource.project_id == project_id,
            ProjectSource.source_id == source_id
        )
        existing_result = await db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            continue  # Already assigned

        # Create assignment
        assignment = ProjectSource(
            project_id=project_id,
            source_id=source_id,
        )
        db.add(assignment)
        assigned_count += 1

    await db.flush()

    return {"assigned": assigned_count}


@router.delete("/{project_id}/knowledge-sources")
async def unassign_knowledge_sources(
    project_id: str,
    request: UnassignSourcesRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Remove knowledge source assignments from a project.

    Only removes assignments for global sources.
    Project-specific sources cannot be unassigned (they belong to the project).
    """
    # Verify project exists
    proj_stmt = select(Project).where(Project.id == project_id)
    proj_result = await db.execute(proj_stmt)
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    removed_count = 0

    for source_id in request.source_ids:
        # Find and delete assignment
        stmt = select(ProjectSource).where(
            ProjectSource.project_id == project_id,
            ProjectSource.source_id == source_id
        )
        result = await db.execute(stmt)
        assignment = result.scalar_one_or_none()

        if assignment:
            await db.delete(assignment)
            removed_count += 1

    await db.flush()

    return {"removed": removed_count}
