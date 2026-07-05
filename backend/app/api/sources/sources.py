"""
Source CRUD endpoints.

Handles creation, listing, updating, and deletion of knowledge sources.
Also includes URL management and file upload functionality.
"""
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.auth import Scope, require_scope
from app.models import Project, ProjectSource, Source, Agent, AgentSource, APIKey
from app.services import IngestionService, run_indexing_task, run_incremental_file_index_task

from .schemas import (
    SourceCreate,
    SourceUpdate,
    SourceResponse,
    AddUrlsRequest,
    RemoveUrlsRequest,
    RemoveFilesRequest,
    AdoptCollectionRequest,
    ProjectInfo,
    AgentInfo,
)
from .helpers import (
    get_sub_source_counts,
    get_sub_source_document_counts,
    get_sub_source_chunk_counts,
    source_to_response,
)

router = APIRouter()
settings = get_settings()

# Magic byte signatures for file types we accept.
# Each entry: extension → list of byte sequences that the file must start with.
# If a file's extension is not listed here it passes through without a magic check.
_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".pptx": [b"PK\x03\x04"],   # ZIP container (Office Open XML)
    ".docx": [b"PK\x03\x04"],   # ZIP container (Office Open XML)
}


def _validate_magic_bytes(ext: str, content: bytes, filename: str) -> None:
    """Raise HTTPException 400 if file content doesn't match expected magic bytes.

    Plain-text types (.txt, .md, .html, .ampscript) are not checked because they
    have no canonical binary signature.
    """
    signatures = _MAGIC_BYTES.get(ext)
    if not signatures:
        return  # No magic check for this type

    if not any(content.startswith(sig) for sig in signatures):
        raise HTTPException(
            status_code=400,
            detail=(
                f"File content does not match declared type '{ext}': {filename}. "
                "The file may be corrupt or the extension may be incorrect."
            ),
        )


# ==================== List Sources ====================

@router.get("/", response_model=list[SourceResponse])
async def list_knowledge_sources(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    List all knowledge sources with project assignment info.

    If project_id is provided, filters to that project's sources + assigned global sources.
    Otherwise returns all sources.
    """
    service = IngestionService(db)
    sources = await service.list_sources(project_id)

    sub_counts = await get_sub_source_counts(db, [s.id for s in sources])
    sub_doc_counts = await get_sub_source_document_counts(db, sources)
    sub_chunk_counts = await get_sub_source_chunk_counts(db, sources)

    # Build response with project assignment and agent binding info
    responses = []
    for source in sources:
        assigned_projects = []
        owner_project = None
        bound_agents = []

        if source.project_id:
            # Project-specific source - get owner project info
            proj_stmt = select(Project).where(Project.id == source.project_id)
            proj_result = await db.execute(proj_stmt)
            proj = proj_result.scalar_one_or_none()
            if proj:
                owner_project = ProjectInfo(id=proj.id, name=proj.name)
        else:
            # Global source - get assigned projects
            assign_stmt = (
                select(Project)
                .join(ProjectSource, Project.id == ProjectSource.project_id)
                .where(ProjectSource.source_id == source.id)
            )
            assign_result = await db.execute(assign_stmt)
            assigned_projs = assign_result.scalars().all()
            assigned_projects = [ProjectInfo(id=p.id, name=p.name) for p in assigned_projs]

        # Get agents bound to this knowledge source
        agent_stmt = (
            select(Agent)
            .join(AgentSource, Agent.id == AgentSource.agent_id)
            .where(AgentSource.source_id == source.id)
        )
        agent_result = await db.execute(agent_stmt)
        bound_agent_objs = agent_result.scalars().all()
        bound_agents = [
            AgentInfo(id=a.id, name=a.name)
            for a in bound_agent_objs
        ]

        responses.append(source_to_response(
            source, assigned_projects, owner_project, bound_agents,
            sub_source_count=sub_counts.get(source.id, 0),
            document_count_override=sub_doc_counts.get(source.id),
            chunk_count_override=sub_chunk_counts.get(source.id),
        ))

    return responses


@router.get("/global", response_model=list[SourceResponse])
async def list_global_sources(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    List all global knowledge sources with their project assignments.

    Global sources have project_id = NULL and can be assigned to multiple projects.
    """
    service = IngestionService(db)
    sources = await service.list_global_sources()

    sub_counts = await get_sub_source_counts(db, [s.id for s in sources])
    sub_doc_counts = await get_sub_source_document_counts(db, sources)
    sub_chunk_counts = await get_sub_source_chunk_counts(db, sources)

    # Build response with project assignment and agent binding info
    responses = []
    for source in sources:
        assign_stmt = (
            select(Project)
            .join(ProjectSource, Project.id == ProjectSource.project_id)
            .where(ProjectSource.source_id == source.id)
        )
        assign_result = await db.execute(assign_stmt)
        assigned_projs = assign_result.scalars().all()
        assigned_projects = [ProjectInfo(id=p.id, name=p.name) for p in assigned_projs]

        # Get agents bound to this knowledge source
        agent_stmt = (
            select(Agent)
            .join(AgentSource, Agent.id == AgentSource.agent_id)
            .where(AgentSource.source_id == source.id)
        )
        agent_result = await db.execute(agent_stmt)
        bound_agent_objs = agent_result.scalars().all()
        bound_agents = [
            AgentInfo(id=a.id, name=a.name)
            for a in bound_agent_objs
        ]

        responses.append(source_to_response(
            source, assigned_projects, None, bound_agents,
            sub_source_count=sub_counts.get(source.id, 0),
            document_count_override=sub_doc_counts.get(source.id),
            chunk_count_override=sub_chunk_counts.get(source.id),
        ))

    return responses


# ==================== Create Sources ====================

def _validate_directory_path(source_path: str) -> None:
    """Raise HTTPException 400 if source_path doesn't exist or isn't a readable directory."""
    p = Path(source_path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Path not found or not a directory: {source_path}")
    if not os.access(p, os.R_OK):
        raise HTTPException(status_code=400, detail=f"Path not found or unreadable: {source_path}")


@router.post("/", response_model=SourceResponse, status_code=201)
async def add_knowledge_source(
    source: SourceCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Add a new knowledge source for indexing."""
    if source.source_type == "directory" and source.watch_enabled:
        _validate_directory_path(source.source_path)

    if source.source_type == "youtube":
        from app.core.url_validator import validate_youtube_channel_url
        try:
            validate_youtube_channel_url(source.source_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    service = IngestionService(db)

    try:
        db_source = await service.create_source(
            name=source.name,
            source_type=source.source_type,
            source_path=source.source_path,
            project_id=source.project_id,
            selected_urls=source.selected_urls,
            description=source.description,
            freshness_policy=source.freshness_policy,
            stale_after_days=source.stale_after_days,
            refresh_interval_days=source.refresh_interval_days,
            enrichment_enabled=source.enrichment_enabled,
            enrichment_taxonomy_id=source.enrichment_taxonomy_id,
            enrichment_model=source.enrichment_model,
            parent_source_id=source.parent_source_id,
            path_prefix=source.path_prefix,
            path_excludes=source.path_excludes,
            youtube_backfill_mode=source.youtube_backfill_mode,
            youtube_recent_count=source.youtube_recent_count,
        )
        await db.commit()
        await db.refresh(db_source)

        if source.source_type == "directory" and source.watch_enabled:
            from app.services.ingestion.watcher import watcher_manager
            try:
                await watcher_manager.start_watcher(db_source.id)
            except Exception as exc:
                import structlog as _structlog
                _structlog.get_logger().warning("Auto-start watcher failed on create", source_id=db_source.id, error=str(exc))

        sub_doc_counts = await get_sub_source_document_counts(db, [db_source])
        sub_chunk_counts = await get_sub_source_chunk_counts(db, [db_source])
        return source_to_response(
            db_source,
            document_count_override=sub_doc_counts.get(db_source.id),
            chunk_count_override=sub_chunk_counts.get(db_source.id),
        )
    except HTTPException:
        raise
    except ValueError as e:
        # "not found" → 404; anything else (validation, bad config) → 400
        status = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/upload", response_model=SourceResponse, status_code=201)
async def upload_file_source(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    name: str = Form(...),
    project_id: Optional[str] = Form(None),
    embedding_provider: Optional[str] = Form(None),
    embedding_model: Optional[str] = Form(None),
    enrichment_enabled: bool = Form(False),
    enrichment_taxonomy_id: Optional[str] = Form(None),
    enrichment_model: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Upload PDF file(s) and create a knowledge source.
    Files are saved to uploads directory and indexing starts automatically.
    Supports multiple files in a single knowledge source.
    """
    import json

    allowed_extensions = [ext.strip() for ext in settings.allowed_file_extensions.split(",")]
    max_size = settings.max_upload_size_mb * 1024 * 1024
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []  # Track saved files for cleanup on error

    try:
        # Process and save each file
        for file in files:
            file_ext = Path(file.filename).suffix.lower() if file.filename else ""

            if file_ext not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type not allowed: {file.filename}. Allowed types: {', '.join(allowed_extensions)}"
                )

            content = await file.read()

            if len(content) > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: {file.filename}. Maximum size: {settings.max_upload_size_mb}MB"
                )

            # Validate that file content matches the declared extension (magic bytes check).
            _validate_magic_bytes(file_ext, content, file.filename or "")

            # Generate unique filename and save
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = upload_dir / unique_filename

            with open(file_path, "wb") as f:
                f.write(content)

            saved_files.append({
                "path": str(file_path),
                "original_name": file.filename or unique_filename,
                "size_bytes": len(content),
            })

        # Create knowledge source with selected_files
        service = IngestionService(db)

        # Use first file's path as source_path for compatibility, store all in selected_files
        db_source = await service.create_source(
            name=name,
            source_type="file",
            source_path=saved_files[0]["path"] if saved_files else "",
            project_id=project_id,
            selected_files=saved_files,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            enrichment_enabled=enrichment_enabled,
            enrichment_taxonomy_id=enrichment_taxonomy_id,
            enrichment_model=enrichment_model,
        )

        # Start indexing
        await service.start_indexing(db_source.id)

        # Commit before scheduling background task
        await db.commit()

        # Schedule background task
        background_tasks.add_task(run_indexing_task, db_source.id)

        return source_to_response(db_source)

    except HTTPException:
        # Re-raise HTTP exceptions, but clean up files first
        for file_info in saved_files:
            Path(file_info["path"]).unlink(missing_ok=True)
        raise
    except ValueError as e:
        # Clean up files
        for file_info in saved_files:
            Path(file_info["path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Clean up files
        for file_info in saved_files:
            Path(file_info["path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adopt", response_model=SourceResponse, status_code=201)
async def adopt_existing_collection(
    request: AdoptCollectionRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Adopt an existing Qdrant collection as a knowledge source.

    This allows you to add a collection that was created outside of AgentStudio
    (or previously unlinked) back into the knowledge base. You must specify
    the embedding configuration that was used to create the collection.
    """
    from app.services.ingestion_service import get_qdrant_client
    import structlog

    logger = structlog.get_logger()

    # Check if collection already linked to a source
    stmt = select(Source).where(Source.collection_name == request.collection_name)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Collection already linked to source '{existing.name}'"
        )

    # Verify collection exists in Qdrant
    try:
        client = get_qdrant_client()
        collection_info = client.get_collection(request.collection_name)
    except Exception as e:
        logger.error("Failed to get collection", collection=request.collection_name, error=str(e))
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{request.collection_name}' not found in Qdrant"
        )

    # Validate project if provided
    if request.project_id:
        proj_stmt = select(Project).where(Project.id == request.project_id)
        proj_result = await db.execute(proj_stmt)
        if not proj_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Project not found")

    # Create knowledge source record
    source = Source(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        source_type="collection",  # Special type for adopted collections
        source_path=request.collection_name,  # Store collection name as path
        project_id=request.project_id,
        collection_name=request.collection_name,
        status="indexed",  # Already has data
        document_count=0,  # We don't know the exact doc count
        chunk_count=collection_info.points_count or 0,
        embedding_provider=request.embedding_provider,
        embedding_model=request.embedding_model,
        embedding_dimensions=request.embedding_dimensions,
        enrichment_enabled=request.enrichment_enabled,
        enrichment_taxonomy_id=request.enrichment_taxonomy_id,
        enrichment_model=request.enrichment_model,
    )

    db.add(source)
    await db.commit()
    await db.refresh(source)

    logger.info(
        "Adopted existing collection",
        source_id=source.id,
        collection_name=request.collection_name,
        points_count=collection_info.points_count,
    )

    return source_to_response(source)


# ==================== Get/Update/Delete Sources ====================

@router.get("/{source_id}", response_model=SourceResponse)
async def get_knowledge_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a specific knowledge source."""
    service = IngestionService(db)
    source = await service.get_source(source_id)

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    sub_counts = await get_sub_source_counts(db, [source.id])
    sub_doc_counts = await get_sub_source_document_counts(db, [source])
    sub_chunk_counts = await get_sub_source_chunk_counts(db, [source])
    return source_to_response(
        source,
        sub_source_count=sub_counts.get(source.id, 0),
        document_count_override=sub_doc_counts.get(source.id),
        chunk_count_override=sub_chunk_counts.get(source.id),
    )


@router.put("/{source_id}", response_model=SourceResponse)
async def update_knowledge_source(
    source_id: str,
    update: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update a knowledge source's metadata and configuration."""
    import structlog as _sl
    _log = _sl.get_logger()

    # Path validation when enabling watching
    if update.watch_enabled:
        existing_stmt = select(Source).where(Source.id == source_id)
        existing_result = await db.execute(existing_stmt)
        existing_source = existing_result.scalar_one_or_none()
        if existing_source and existing_source.source_type == "directory":
            path_to_check = existing_source.source_path
            if not Path(path_to_check).exists() or not Path(path_to_check).is_dir():
                raise HTTPException(status_code=400, detail=f"Path not found or not a directory: {path_to_check}")
            if not os.access(path_to_check, os.R_OK):
                raise HTTPException(status_code=400, detail=f"Path not found or unreadable: {path_to_check}")

    service = IngestionService(db)

    try:
        source = await service.update_source(
            source_id=source_id,
            name=update.name,
            description=update.description,
            watch_enabled=update.watch_enabled,
            watch_extensions=update.watch_extensions,
            watch_mode=update.watch_mode,
            watch_poll_interval_seconds=update.watch_poll_interval_seconds,
            watch_debounce_seconds=update.watch_debounce_seconds,
            watch_max_file_size_mb=update.watch_max_file_size_mb,
            watch_depth=update.watch_depth,
            enrichment_enabled=update.enrichment_enabled,
            enrichment_taxonomy_id=update.enrichment_taxonomy_id,
            enrichment_model=update.enrichment_model,
            freshness_policy=update.freshness_policy,
            stale_after_days=update.stale_after_days,
            refresh_interval_days=update.refresh_interval_days,
            youtube_backfill_mode=update.youtube_backfill_mode,
            youtube_recent_count=update.youtube_recent_count,
            path_prefix=update.path_prefix,
            path_excludes=update.path_excludes,
        )
    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status, detail=str(e))

    # Commit so the watcher manager's separate DB session can see the change
    await db.commit()
    await db.refresh(source)

    from app.services.ingestion.watcher import watcher_manager

    watcher_config_changed = any(v is not None for v in [
        update.watch_extensions, update.watch_mode, update.watch_poll_interval_seconds,
        update.watch_debounce_seconds, update.watch_max_file_size_mb, update.watch_depth,
    ])

    try:
        if update.watch_enabled is False:
            await watcher_manager.stop_watcher(source_id)
        elif update.watch_enabled is True:
            # Stop first to pick up new config, then restart
            await watcher_manager.stop_watcher(source_id)
            await watcher_manager.start_watcher(source_id)
        elif watcher_config_changed and source_id in watcher_manager._watchers:
            # Config changed while watcher is running — restart to apply
            await watcher_manager.stop_watcher(source_id)
            await watcher_manager.start_watcher(source_id)
    except Exception as exc:
        _log.warning("Watcher control failed during update", source_id=source_id, error=str(exc))

    sub_doc_counts = await get_sub_source_document_counts(db, [source])
    sub_chunk_counts = await get_sub_source_chunk_counts(db, [source])
    return source_to_response(
        source,
        document_count_override=sub_doc_counts.get(source.id),
        chunk_count_override=sub_chunk_counts.get(source.id),
    )


@router.delete("/{source_id}", status_code=204)
async def remove_knowledge_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Remove a knowledge source and its indexed documents."""
    import json

    service = IngestionService(db)

    # Get source first to check if it's a file that needs cleanup
    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Delete uploaded files if this is a file source
    if source.source_type == "file":
        files_to_delete = []

        # Check selected_files first (multi-file)
        if source.selected_files:
            try:
                files_to_delete = [f["path"] for f in json.loads(source.selected_files)]
            except (json.JSONDecodeError, KeyError):
                pass

        # Fall back to source_path for legacy single-file
        if not files_to_delete and source.source_path:
            files_to_delete = [source.source_path]

        # Delete each file
        for file_path_str in files_to_delete:
            file_path = Path(file_path_str)
            if file_path.exists() and str(file_path).startswith(settings.upload_dir):
                try:
                    file_path.unlink()
                except Exception:
                    pass  # Best effort cleanup

    try:
        await service.delete_source(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return None


# ==================== URL Management ====================

@router.post("/{source_id}/urls", response_model=SourceResponse)
async def add_urls_to_source(
    source_id: str,
    request: AddUrlsRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Add new URLs to an existing URL source."""
    service = IngestionService(db)

    try:
        source = await service.add_urls_to_source(source_id, request.urls)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return source_to_response(source)


@router.delete("/{source_id}/urls", response_model=SourceResponse)
async def remove_urls_from_source(
    source_id: str,
    request: RemoveUrlsRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Remove URLs from an existing URL source and delete their vectors."""
    service = IngestionService(db)

    try:
        source = await service.remove_urls_from_source(source_id, request.urls)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return source_to_response(source)


# ==================== File Management ====================

@router.post("/{source_id}/files", response_model=SourceResponse)
async def add_files_to_source(
    source_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Add files to an existing file source.

    Files are saved to disk and added to the source's file list immediately.
    If indexing is not currently active, incremental indexing starts automatically
    (only the new files are indexed — existing vectors are preserved).
    If indexing IS active, files are saved for the next indexing pass.
    """
    allowed_extensions = [ext.strip() for ext in settings.allowed_file_extensions.split(",")]
    max_size = settings.max_upload_size_mb * 1024 * 1024
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    service = IngestionService(db)

    # Verify source exists and is file type
    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.source_type != "file":
        raise HTTPException(status_code=400, detail="Can only add files to file-type sources")

    saved_files = []

    try:
        # Process and save each file
        for file in files:
            file_ext = Path(file.filename).suffix.lower() if file.filename else ""

            if file_ext not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type not allowed: {file.filename}. Allowed types: {', '.join(allowed_extensions)}"
                )

            content = await file.read()

            if len(content) > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: {file.filename}. Maximum size: {settings.max_upload_size_mb}MB"
                )

            # Validate that file content matches the declared extension (magic bytes check).
            _validate_magic_bytes(file_ext, content, file.filename or "")

            # Generate unique filename and save
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = upload_dir / unique_filename

            with open(file_path, "wb") as f:
                f.write(content)

            saved_files.append({
                "path": str(file_path),
                "original_name": file.filename or unique_filename,
                "size_bytes": len(content),
            })

        # Add files to source metadata (always succeeds, no lock contention)
        updated_source = await service.add_files_to_source(source_id, saved_files)
        await db.commit()

        # Only start incremental indexing if not already indexing
        if source.status != "indexing":
            background_tasks.add_task(
                run_incremental_file_index_task, source_id, saved_files
            )

        return source_to_response(updated_source)

    except HTTPException:
        for file_info in saved_files:
            Path(file_info["path"]).unlink(missing_ok=True)
        raise
    except ValueError as e:
        for file_info in saved_files:
            Path(file_info["path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        for file_info in saved_files:
            Path(file_info["path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{source_id}/files", response_model=SourceResponse)
async def remove_files_from_source(
    source_id: str,
    request: RemoveFilesRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Remove files from an existing file source and delete their vectors."""
    service = IngestionService(db)

    try:
        source = await service.remove_files_from_source(source_id, request.file_paths)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return source_to_response(source)
