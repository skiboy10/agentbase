"""
Library API

Endpoints for managing Library (KnowledgeBase) entities — each Library owns one Qdrant
collection and can aggregate multiple Sources.

Routes:
    POST   /api/libraries
    GET    /api/libraries
    GET    /api/libraries/{library_id}
    PATCH  /api/libraries/{library_id}
    DELETE /api/libraries/{library_id}
    GET    /api/libraries/{library_id}/sources
    POST   /api/libraries/{library_id}/sources
    DELETE /api/libraries/{library_id}/sources/{source_id}
    POST   /api/libraries/{library_id}/recalculate-stats
    GET    /api/libraries/{library_id}/documents
    GET    /api/libraries/{library_id}/documents/{doc_id}
    GET    /api/libraries/{library_id}/documents/{doc_id}/text
    DELETE /api/libraries/{library_id}/documents/{doc_id}
    POST   /api/libraries/{library_id}/chat
"""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

import structlog
from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services.library import LibraryService, DocumentService
from app.services.library.service import EmbeddingMismatchError
from app.services.library_chat import LibraryChatService
from app.api.sources.helpers import source_to_response
from app.api.sources.schemas import SourceResponse

logger = structlog.get_logger()

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ============================================================
# Request / Response Schemas
# ============================================================

class LibraryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    # Embedding config is optional — the first source added to the library
    # locks in the embedding model. Explicitly passing it reserves the model
    # up front (useful if source_ids are provided at create time).
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None
    taxonomy_id: Optional[str] = None
    enrichment_model: Optional[str] = None
    source_ids: Optional[list[str]] = None


class LibraryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    taxonomy_id: Optional[str] = None
    enrichment_model: Optional[str] = None
    status: Optional[str] = None


class AddSourceRequest(BaseModel):
    source_id: str


class LibraryResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    project_id: Optional[str]
    collection_name: str
    # Embedding fields are null for newly-created libraries with no sources yet.
    # They are locked in when the first source is added.
    embedding_provider: Optional[str]
    embedding_model: Optional[str]
    embedding_dimensions: Optional[int]
    taxonomy_id: Optional[str]
    enrichment_model: Optional[str]
    source_count: int
    document_count: int
    chunk_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    # Minimal source list
    source_ids: list[str] = []

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: str
    library_id: str
    source_id: Optional[str]
    source_name: Optional[str] = None
    document_id: str
    title: Optional[str]
    file_path: Optional[str]
    url: Optional[str]
    file_type: Optional[str]
    text_length: int
    content_hash: Optional[str]
    document_type: Optional[str]
    chunk_count: int
    status: str
    error_message: Optional[str]
    indexed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # full_text excluded by default (use /text endpoint)

    class Config:
        from_attributes = True


def _document_to_response(doc) -> "DocumentResponse":
    """Build a DocumentResponse from an ORM Document.

    Resolves ``source_name`` from the eagerly loaded ``Document.source``
    relationship (None when source_id is null due to ON DELETE SET NULL).
    """
    return DocumentResponse(
        id=doc.id,
        library_id=doc.library_id,
        source_id=doc.source_id,
        source_name=doc.source.name if doc.source else None,
        document_id=doc.document_id,
        title=doc.title,
        file_path=doc.file_path,
        url=doc.url,
        file_type=doc.file_type,
        text_length=doc.text_length,
        content_hash=doc.content_hash,
        document_type=doc.document_type,
        chunk_count=doc.chunk_count,
        status=doc.status,
        error_message=doc.error_message,
        indexed_at=doc.indexed_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class DocumentTextResponse(BaseModel):
    doc_id: str
    full_text: Optional[str]


def _library_to_response(kb) -> LibraryResponse:
    """Convert ORM KnowledgeBase to response schema."""
    return LibraryResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        project_id=kb.project_id,
        collection_name=kb.collection_name,
        embedding_provider=kb.embedding_provider,
        embedding_model=kb.embedding_model,
        embedding_dimensions=kb.embedding_dimensions,
        taxonomy_id=kb.taxonomy_id,
        enrichment_model=kb.enrichment_model,
        source_count=kb.source_count,
        document_count=kb.document_count,
        chunk_count=kb.chunk_count,
        status=kb.status,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        source_ids=[s.id for s in (kb.sources or [])],
    )


# ============================================================
# Library CRUD
# ============================================================

@router.post("/libraries", response_model=LibraryResponse, status_code=201)
async def create_library(
    payload: LibraryCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Create a new Library and its backing Qdrant collection."""
    service = LibraryService(db)
    try:
        kb = await service.create_kb(
            name=payload.name,
            description=payload.description,
            project_id=payload.project_id,
            embedding_provider=payload.embedding_provider,
            embedding_model=payload.embedding_model,
            embedding_dimensions=payload.embedding_dimensions,
            taxonomy_id=payload.taxonomy_id,
            enrichment_model=payload.enrichment_model,
            source_ids=payload.source_ids,
        )
    except EmbeddingMismatchError as exc:
        raise HTTPException(status_code=409, detail=exc.to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _library_to_response(kb)


@router.get("/libraries", response_model=list[LibraryResponse])
async def list_libraries(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all Libraries. Optionally filter by project_id."""
    service = LibraryService(db)
    kbs = await service.list_kbs(project_id=project_id)
    return [_library_to_response(kb) for kb in kbs]


@router.get("/libraries/{library_id}", response_model=LibraryResponse)
async def get_library(
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a single Library with its source list and stats."""
    service = LibraryService(db)
    kb = await service.get_kb(library_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return _library_to_response(kb)


@router.patch("/libraries/{library_id}", response_model=LibraryResponse)
async def update_library(
    library_id: str,
    payload: LibraryUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update Library metadata (name, description, taxonomy_id, enrichment_model, status)."""
    service = LibraryService(db)
    updates = payload.model_dump(exclude_none=True)
    kb = await service.update_kb(library_id, **updates)
    if kb is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return _library_to_response(kb)


@router.delete("/libraries/{library_id}", status_code=204)
async def delete_library(
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Delete a Library, its Qdrant collection, and all Document records."""
    service = LibraryService(db)
    deleted = await service.delete_kb(library_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Library not found")


# ============================================================
# Source management
# ============================================================

@router.get("/libraries/{library_id}/sources", response_model=list[SourceResponse])
async def list_library_sources(
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all Sources attached to this Library."""
    service = LibraryService(db)
    kb = await service.get_kb(library_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return [source_to_response(s) for s in (kb.sources or [])]


@router.post("/libraries/{library_id}/sources")
async def add_source_to_library(
    library_id: str,
    payload: AddSourceRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Associate an existing Source with this Library.

    Enforces embedding-model compatibility. If the library has no embedding model
    yet, the source's model is locked in. Otherwise the source must match, or a
    409 EMBEDDING_MISMATCH is returned with structured fields describing both
    models and a suggested action — external agents should branch on
    ``error_code == "EMBEDDING_MISMATCH"`` and read ``library`` / ``source`` /
    ``suggested_action`` to adapt.

    Returns ``{bound, already_bound, reindex_queued}``. When the source is
    already indexed, ``reindex_queued`` is true — a background job fans its
    chunks into this library's collection.
    """
    service = LibraryService(db)
    try:
        result = await service.add_source(library_id, payload.source_id)
    except EmbeddingMismatchError as exc:
        raise HTTPException(status_code=409, detail=exc.to_dict())
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Library or source not found",
        )
    return result


@router.delete("/libraries/{library_id}/sources/{source_id}", status_code=204)
async def remove_source_from_library(
    library_id: str,
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Remove a source from this Library (disassociates and deletes its Document records)."""
    service = LibraryService(db)
    ok = await service.remove_source(library_id, source_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Source not found in this library",
        )


@router.post("/libraries/{library_id}/recalculate-stats", response_model=LibraryResponse)
async def recalculate_library_stats(
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Recount source, document, and chunk totals for this Library."""
    service = LibraryService(db)
    kb = await service.recalculate_stats(library_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return _library_to_response(kb)


@router.get("/libraries/{library_id}/coverage")
async def get_library_coverage_report(
    library_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Taxonomy coverage gap analysis for a library.

    Returns per-term chunk counts, percentages, and coverage ratings
    (deep/adequate/thin/none) for the library's linked taxonomy.
    """
    from app.services.library.coverage import get_library_coverage
    return await get_library_coverage(db, library_id)


# ============================================================
# Document endpoints
# ============================================================

class DocumentPageResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


# ============================================================
# Chat schemas
# ============================================================

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatConfig(BaseModel):
    provider: str
    model: str
    top_k: int = 5
    rerank: bool = False
    system_prompt: Optional[str] = None
    search_mode: Literal["hybrid", "vector", "deep"] = "hybrid"
    vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)

class LibraryChatRequest(BaseModel):
    message: str = Field(..., max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list)
    config: ChatConfig

class ChatSourceItem(BaseModel):
    source_id: str
    source_name: str
    url: str
    title: str
    score: float
    preview: str

class LibraryChatResponse(BaseModel):
    answer: str
    sources: list[ChatSourceItem] = []
    model: str


@router.get("/libraries/{library_id}/documents", response_model=DocumentPageResponse)
async def list_documents(
    library_id: str,
    source_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    file_type: Optional[str] = None,
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    List documents for a Library (paginated).

    Optional filters:
    - source_id: restrict to a specific source
    - search: search by title (ILIKE)
    - file_type: filter by file extension
    - document_type: filter by document type
    """
    service = DocumentService(db)
    if search:
        docs = await service.search_documents(library_id, search)
        total = len(docs)
    else:
        docs = await service.list_documents(
            library_id,
            source_id=source_id,
            limit=limit,
            offset=offset,
            file_type=file_type,
            document_type=document_type,
        )
        total = await service.count_documents(
            library_id,
            source_id=source_id,
            file_type=file_type,
            document_type=document_type,
        )
    return DocumentPageResponse(
        documents=[_document_to_response(d) for d in docs],
        total=total,
    )


@router.get("/libraries/{library_id}/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    library_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get document metadata (excludes full_text — use /text for that)."""
    service = DocumentService(db)
    doc = await service.get_document(doc_id)
    if doc is None or doc.library_id != library_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_to_response(doc)


@router.get("/libraries/{library_id}/documents/{doc_id}/text", response_model=DocumentTextResponse)
async def get_document_text(
    library_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Return the full stored text for a document."""
    service = DocumentService(db)
    doc = await service.get_document(doc_id)
    if doc is None or doc.library_id != library_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentTextResponse(doc_id=doc_id, full_text=doc.full_text)


@router.delete("/libraries/{library_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    library_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """
    Delete a document record.

    Note: Qdrant chunk cleanup is NOT performed here. The caller (or a
    background job) must remove corresponding vectors from the collection.
    """
    service = DocumentService(db)
    doc = await service.get_document(doc_id)
    if doc is None or doc.library_id != library_id:
        raise HTTPException(status_code=404, detail="Document not found")
    await service.delete_document(doc_id)


# ============================================================
# Chat endpoint
# ============================================================

@router.post("/libraries/{library_id}/chat", response_model=LibraryChatResponse)
@limiter.limit("30/minute")
async def chat_with_library(
    library_id: str,
    data: LibraryChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    # READ, not WRITE: stateless retrieval + LLM answer, same class as
    # search/deep-search; the per-route rate limit bounds LLM spend.
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """
    Send a message to chat with a library's knowledge base.

    Retrieves relevant chunks, builds conversation context, and calls
    the configured LLM to produce a grounded multi-turn response.
    """
    service = LibraryChatService(db)
    try:
        result = await service.chat(
            library_id=library_id,
            message=data.message,
            history=[{"role": m.role, "content": m.content} for m in data.history],
            config=data.config.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Library chat failed", library_id=library_id, error=str(e))
        raise HTTPException(status_code=500, detail="Chat request failed")

    return LibraryChatResponse(
        answer=result["answer"],
        sources=[ChatSourceItem(**s) for s in result["sources"]],
        model=result["model"],
    )
