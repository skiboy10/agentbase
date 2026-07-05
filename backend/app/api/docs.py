"""
Documentation API routes.

Serves API documentation files.
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter()


def get_project_root() -> Path:
    """Get the project root directory."""
    # In Docker: /app
    # Local: parent of backend/app/api
    docker_path = Path("/app")
    if docker_path.exists() and (docker_path / "API.md").exists():
        return docker_path

    # Local development - go up from backend/app/api
    local_path = Path(__file__).parent.parent.parent.parent
    return local_path


@router.get("/api-reference", response_class=PlainTextResponse)
async def get_api_reference():
    """
    Get the API reference documentation.

    Returns the raw markdown content of API.md.
    """
    project_root = get_project_root()
    api_md_path = project_root / "API.md"

    if not api_md_path.exists():
        raise HTTPException(
            status_code=404,
            detail="API documentation not found"
        )

    try:
        content = api_md_path.read_text(encoding="utf-8")
        return PlainTextResponse(content, media_type="text/markdown")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read API documentation: {str(e)}"
        )
