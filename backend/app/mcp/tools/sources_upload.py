"""
MCP Tools for Source Upload & Ingest

File upload (single/multi), add-files-to-source, and GitHub source creation.
"""

import asyncio
import base64
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiofiles
import structlog

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.core.auth import Scope, check_mcp_scope
from app.core.events import publish_source_event
from app.services import IngestionService, run_indexing_task
from app.services.ingestion import QueueManager

from app.mcp.tools.sources import _source_to_dict

logger = structlog.get_logger()


@mcp.tool(
    description=(
        "Upload a base64-encoded file to create and index a source. "
        "For multiple files, use agentbase_upload_source_files instead."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_upload_source_file(
    file_content: str,
    filename: str,
    name: Optional[str] = None,
    project_id: Optional[str] = None,
    embedding_provider: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> dict:
    """Upload a file and create a source. Returns source_id, status, queue_position."""
    check_mcp_scope(Scope.WRITE)
    from app.core.config import get_settings

    settings = get_settings()

    # Validate extension
    ext = Path(filename).suffix.lower()
    allowed = [e.strip() for e in settings.allowed_file_extensions.split(",")]
    if ext not in allowed:
        return {"error": f"File type {ext} not allowed. Allowed: {allowed}"}

    # Check estimated size before decoding to avoid memory exhaustion
    estimated_size = len(file_content) * 3 / 4
    if estimated_size / (1024 * 1024) > settings.max_upload_size_mb:
        return {
            "error": f"File too large: ~{estimated_size/(1024*1024):.1f}MB > {settings.max_upload_size_mb}MB limit"
        }

    # Decode file content
    try:
        file_bytes = base64.b64decode(file_content)
    except Exception as e:
        return {"error": f"Invalid base64 content: {e}"}

    # Check exact file size
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        return {
            "error": f"File too large: {size_mb:.1f}MB > {settings.max_upload_size_mb}MB limit"
        }

    # Save to upload directory
    os.makedirs(settings.upload_dir, exist_ok=True)
    unique_filename = f"{uuid4()}{ext}"
    file_path = os.path.join(settings.upload_dir, unique_filename)

    try:
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_bytes)
    except Exception as e:
        return {"error": f"Failed to save file: {e}"}

    # Create knowledge source and manage queue
    source_name = name or Path(filename).stem
    async with async_session_maker() as db:
        service = IngestionService(db)
        queue_manager = QueueManager(db)

        try:
            source = await service.create_source(
                name=source_name,
                source_type="file",
                source_path=file_path,
                project_id=project_id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )

            # Check queue and start or queue
            can_start = await queue_manager.can_start_indexing()
            if can_start:
                await service.start_indexing(source.id)
                await db.commit()
                asyncio.create_task(run_indexing_task(source.id))
                status = "indexing"
                queue_position = 0
            else:
                source.status = "queued"
                await db.commit()
                queue_position = await queue_manager.get_queue_position(source.id)
                status = "queued"

            active_count = await queue_manager.get_active_count()

            logger.info(
                "MCP: Uploaded knowledge file",
                source_id=source.id,
                name=source_name,
                status=status,
                queue_position=queue_position,
            )

            # Publish event for UI update
            await publish_source_event(
                "created", source.id, {"name": source_name}, source="mcp"
            )

            return {
                "source_id": source.id,
                "name": source_name,
                "status": status,
                "queue_position": queue_position,
                "active_jobs": active_count,
                "max_concurrent": settings.max_concurrent_indexing,
            }
        except ValueError as e:
            # Clean up saved file on error
            try:
                os.remove(file_path)
            except OSError:
                pass
            return {"error": str(e)}


@mcp.tool(
    description="Upload multiple base64 files as a single source. Each file needs 'content' and 'filename'.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_upload_source_files(
    files: list[dict],
    name: str,
    project_id: Optional[str] = None,
    embedding_provider: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> dict:
    """Upload multiple files as one source. Returns source_id, file_count, status."""
    check_mcp_scope(Scope.WRITE)
    from app.core.config import get_settings

    settings = get_settings()
    allowed = [e.strip() for e in settings.allowed_file_extensions.split(",")]
    max_size = settings.max_upload_size_mb * 1024 * 1024

    if not files:
        return {"error": "No files provided"}

    saved_files = []

    try:
        # Validate and save each file
        for file_info in files:
            content = file_info.get("content")
            filename = file_info.get("filename")

            if not content or not filename:
                return {"error": "Each file must have 'content' and 'filename'"}

            ext = Path(filename).suffix.lower()
            if ext not in allowed:
                return {"error": f"File type {ext} not allowed for {filename}"}

            # Check estimated size before decoding
            estimated_size = len(content) * 3 / 4
            if estimated_size > max_size:
                return {"error": f"File {filename} too large: ~{estimated_size/(1024*1024):.1f}MB"}

            # Decode
            try:
                file_bytes = base64.b64decode(content)
            except Exception as e:
                return {"error": f"Invalid base64 for {filename}: {e}"}

            # Check exact size
            if len(file_bytes) > max_size:
                return {"error": f"File {filename} too large: {len(file_bytes)/(1024*1024):.1f}MB"}

            # Save
            os.makedirs(settings.upload_dir, exist_ok=True)
            unique_filename = f"{uuid4()}{ext}"
            file_path = os.path.join(settings.upload_dir, unique_filename)

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_bytes)

            saved_files.append({
                "path": file_path,
                "original_name": filename,
                "size_bytes": len(file_bytes),
            })

        # Create knowledge source with all files
        async with async_session_maker() as db:
            service = IngestionService(db)
            queue_manager = QueueManager(db)

            source = await service.create_source(
                name=name,
                source_type="file",
                source_path=saved_files[0]["path"],  # First file as primary
                project_id=project_id,
                selected_files=saved_files,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )

            # Check queue and start or queue
            can_start = await queue_manager.can_start_indexing()
            if can_start:
                await service.start_indexing(source.id)
                await db.commit()
                asyncio.create_task(run_indexing_task(source.id))
                status = "indexing"
                queue_position = 0
            else:
                source.status = "queued"
                await db.commit()
                queue_position = await queue_manager.get_queue_position(source.id)
                status = "queued"

            active_count = await queue_manager.get_active_count()

            logger.info(
                "MCP: Uploaded multiple knowledge files",
                source_id=source.id,
                name=name,
                file_count=len(saved_files),
                status=status,
            )

            await publish_source_event(
                "created", source.id, {"name": name}, source="mcp"
            )

            return {
                "source_id": source.id,
                "name": name,
                "file_count": len(saved_files),
                "status": status,
                "queue_position": queue_position,
                "active_jobs": active_count,
                "max_concurrent": settings.max_concurrent_indexing,
            }

    except Exception as e:
        # Clean up saved files on error
        for f in saved_files:
            try:
                os.remove(f["path"])
            except OSError:
                pass
        return {"error": str(e)}


@mcp.tool(
    description="Add base64 files to an existing file-type source and trigger re-indexing.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def agentbase_add_files_to_source(
    source_id: str,
    files: list[dict],
) -> dict:
    """Add files to an existing source. Each file needs 'content' and 'filename'."""
    check_mcp_scope(Scope.WRITE)
    from app.core.config import get_settings

    settings = get_settings()
    allowed = [e.strip() for e in settings.allowed_file_extensions.split(",")]
    max_size = settings.max_upload_size_mb * 1024 * 1024

    if not files:
        return {"error": "No files provided"}

    saved_files = []

    try:
        # Validate and save each file
        for file_info in files:
            content = file_info.get("content")
            filename = file_info.get("filename")

            if not content or not filename:
                return {"error": "Each file must have 'content' and 'filename'"}

            ext = Path(filename).suffix.lower()
            if ext not in allowed:
                return {"error": f"File type {ext} not allowed for {filename}"}

            # Check estimated size before decoding
            estimated_size = len(content) * 3 / 4
            if estimated_size > max_size:
                return {"error": f"File {filename} too large: ~{estimated_size/(1024*1024):.1f}MB"}

            try:
                file_bytes = base64.b64decode(content)
            except Exception as e:
                return {"error": f"Invalid base64 for {filename}: {e}"}

            if len(file_bytes) > max_size:
                return {"error": f"File {filename} too large"}

            os.makedirs(settings.upload_dir, exist_ok=True)
            unique_filename = f"{uuid4()}{ext}"
            file_path = os.path.join(settings.upload_dir, unique_filename)

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_bytes)

            saved_files.append({
                "path": file_path,
                "original_name": filename,
                "size_bytes": len(file_bytes),
            })

        # Add files to source and trigger re-indexing
        async with async_session_maker() as db:
            service = IngestionService(db)

            source = await service.get_source(source_id)
            if not source:
                for f in saved_files:
                    try:
                        os.remove(f["path"])
                    except OSError:
                        pass
                return {"error": f"Source not found: {source_id}"}

            if source.source_type != "file":
                for f in saved_files:
                    try:
                        os.remove(f["path"])
                    except OSError:
                        pass
                return {"error": "Can only add files to file-type sources"}

            updated_source = await service.add_files_to_source(source_id, saved_files)

            # Start re-indexing
            await service.start_indexing(source_id)
            await db.commit()
            asyncio.create_task(run_indexing_task(source_id))

            logger.info(
                "MCP: Added files to knowledge source",
                source_id=source_id,
                file_count=len(saved_files),
            )

            await publish_source_event(
                "updated", source_id, {"files_added": len(saved_files)}, source="mcp"
            )

            return {
                "source_id": source_id,
                "files_added": len(saved_files),
                "status": "indexing",
                "source": _source_to_dict(updated_source),
            }

    except Exception as e:
        for f in saved_files:
            try:
                os.remove(f["path"])
            except OSError:
                pass
        return {"error": str(e)}


# Note: ``create_github_source`` was removed in #104. The GitHub indexer was
# never wired into the KB-aware Document pipeline and had no live sources in
# the production DB. If GitHub ingestion returns, prefer building it on top
# of the URL indexer + a repo-tree expander rather than a parallel indexer.
