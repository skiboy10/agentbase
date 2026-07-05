"""
MCP Tools for Project Management (DEPRECATED)

Projects are deprecated — use Libraries and Sources directly.
These tools remain for backward compatibility.
"""

from typing import Optional
import structlog
from sqlalchemy import select

from app.mcp.server import mcp
from app.core.auth import Scope, check_mcp_scope
from app.core.database import async_session_maker
from app.models import Project

logger = structlog.get_logger()


def _project_to_dict(project: Project) -> dict:
    """Convert Project model to dict."""
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


@mcp.tool(
    description=(
        "[DEPRECATED] List all projects. "
        "Projects are deprecated — use agentbase_list_sources and agentbase_list_libraries instead."
    ),
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_projects() -> list[dict]:
    """List all projects (deprecated)."""
    async with async_session_maker() as db:
        stmt = select(Project).order_by(Project.name)
        result = await db.execute(stmt)
        projects = result.scalars().all()
        return [_project_to_dict(project) for project in projects]


@mcp.tool(
    description=(
        "[DEPRECATED] Get a project by ID. "
        "Projects are deprecated — use agentbase_get_source or agentbase_get_library instead."
    ),
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_get_project(project_id: str) -> dict:
    """Get project details (deprecated)."""
    async with async_session_maker() as db:
        stmt = select(Project).where(Project.id == project_id)
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            return {"error": f"Project not found: {project_id}"}
        return _project_to_dict(project)


@mcp.tool(
    description=(
        "[DEPRECATED] Create a project. "
        "Projects are deprecated — use agentbase_create_library to organize sources."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_create_project(
    name: str,
    description: Optional[str] = None,
) -> dict:
    """Create a project (deprecated)."""
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        project = Project(
            name=name,
            description=description,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)

        logger.info("MCP: Created project", project_id=project.id, name=name)
        return _project_to_dict(project)
