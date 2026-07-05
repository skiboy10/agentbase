"""
Taxonomy API endpoints.

Provides taxonomy CRUD, term management, coverage analytics,
term suggestions, and stale document detection.

Routes:
  GET    /api/taxonomies                              list all
  POST   /api/taxonomies                              create
  GET    /api/taxonomies/{id}                         get one
  PATCH  /api/taxonomies/{id}                         update
  DELETE /api/taxonomies/{id}                         delete

  GET    /api/taxonomies/{id}/terms                   list terms
  POST   /api/taxonomies/{id}/terms                   add term
  PATCH  /api/taxonomies/{id}/terms/{term_id}         update term
  DELETE /api/taxonomies/{id}/terms/{term_id}         delete term

  GET    /api/taxonomies/{id}/coverage                coverage analytics
  GET    /api/taxonomies/{id}/stale                   list stale docs
  GET    /api/taxonomies/{id}/stale/count             count stale docs

  GET    /api/taxonomies/{id}/suggestions             list pending suggestions
  POST   /api/taxonomies/{id}/suggestions/{sid}/approve  approve
  POST   /api/taxonomies/{id}/suggestions/{sid}/reject   reject
  POST   /api/taxonomies/{id}/suggestions/{sid}/merge    merge into existing term
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services.taxonomy import (
    TaxonomyService,
    TaxonomySuggestionService,
    TaxonomyCoverageService,
)

router = APIRouter()


# ============================================================
# Pydantic Schemas
# ============================================================

class TaxonomyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None


class TaxonomyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class TaxonomyResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    version: int = 1
    created_at: str
    updated_at: str
    term_count: int = 0

    class Config:
        from_attributes = True


class TermCreate(BaseModel):
    facet: str
    value: str
    label: Optional[str] = None
    keywords: Optional[list] = None
    sort_order: int = 0


class TermUpdate(BaseModel):
    label: Optional[str] = None
    keywords: Optional[list] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class TermResponse(BaseModel):
    id: str
    taxonomy_id: str
    facet: str
    value: str
    parent_value: Optional[str] = None
    keywords: Optional[list] = None
    sort_order: int = 0
    created_at: str

    class Config:
        from_attributes = True


class SuggestionResponse(BaseModel):
    id: str
    taxonomy_id: str
    facet: str
    suggested_value: str
    frequency: int
    sample_document_ids: Optional[list]
    status: str
    merged_into: Optional[str]
    created_at: str
    reviewed_at: Optional[str]

    class Config:
        from_attributes = True


class MergeRequest(BaseModel):
    merge_into_value: str


class DocumentContentSummary(BaseModel):
    id: str
    source_id: str
    file_id: str  # maps to DocumentContent.url (the unique file identifier)
    title: Optional[str]
    classification: Optional[dict]
    classification_taxonomy_version: Optional[int]
    updated_at: str

    class Config:
        from_attributes = True


# ============================================================
# Helper converters
# ============================================================

def _taxonomy_to_response(taxonomy, term_count: int = 0) -> TaxonomyResponse:
    return TaxonomyResponse(
        id=taxonomy.id,
        name=taxonomy.name,
        description=taxonomy.description,
        project_id=getattr(taxonomy, 'project_id', None),
        version=getattr(taxonomy, 'version', 1),
        created_at=taxonomy.created_at.isoformat() if taxonomy.created_at else '',
        updated_at=taxonomy.updated_at.isoformat() if taxonomy.updated_at else '',
        term_count=term_count,
    )


def _term_to_response(term) -> TermResponse:
    return TermResponse(
        id=term.id,
        taxonomy_id=term.taxonomy_id,
        facet=term.facet,
        value=term.value,
        parent_value=getattr(term, 'parent_value', None),
        keywords=term.keywords,
        sort_order=term.sort_order or 0,
        created_at=term.created_at.isoformat() if term.created_at else '',
    )


def _suggestion_to_response(sug) -> SuggestionResponse:
    return SuggestionResponse(
        id=sug.id,
        taxonomy_id=sug.taxonomy_id,
        facet=sug.facet,
        suggested_value=sug.suggested_value,
        frequency=sug.frequency,
        sample_document_ids=sug.sample_document_ids,
        status=sug.status,
        merged_into=sug.merged_into,
        created_at=sug.created_at.isoformat(),
        reviewed_at=sug.reviewed_at.isoformat() if sug.reviewed_at else None,
    )


def _doc_to_summary(doc) -> DocumentContentSummary:
    return DocumentContentSummary(
        id=doc.id,
        source_id=doc.source_id,
        file_id=doc.url,  # url is the unique file identifier in DocumentContent
        title=doc.title,
        classification=doc.classification,
        classification_taxonomy_version=getattr(doc, 'classification_taxonomy_version', None),
        updated_at=doc.scraped_at.isoformat() if hasattr(doc, 'scraped_at') else '',
    )


# ============================================================
# Taxonomy CRUD
# ============================================================

@router.get("/", response_model=list[TaxonomyResponse])
async def list_taxonomies(
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all taxonomies, optionally filtered by project."""
    svc = TaxonomyService()
    rows = await svc.list_taxonomies(db, project_id=project_id)
    return [_taxonomy_to_response(t, count) for t, count in rows]


@router.post("/", response_model=TaxonomyResponse, status_code=201)
async def create_taxonomy(
    body: TaxonomyCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Create a new taxonomy."""
    svc = TaxonomyService()
    taxonomy = await svc.create_taxonomy(db,
        name=body.name,
        description=body.description,
        project_id=body.project_id,
    )
    return _taxonomy_to_response(taxonomy, term_count=0)


@router.get("/{taxonomy_id}", response_model=TaxonomyResponse)
async def get_taxonomy(
    taxonomy_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a single taxonomy."""
    svc = TaxonomyService()
    taxonomy = await svc.get_taxonomy(db, taxonomy_id)
    if not taxonomy:
        raise HTTPException(status_code=404, detail="Taxonomy not found")
    return _taxonomy_to_response(taxonomy, term_count=len(taxonomy.terms or []))


@router.patch("/{taxonomy_id}", response_model=TaxonomyResponse)
async def update_taxonomy(
    taxonomy_id: str,
    body: TaxonomyUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update taxonomy metadata."""
    svc = TaxonomyService()
    taxonomy = await svc.update_taxonomy(db,
        taxonomy_id,
        name=body.name,
        description=body.description,
    )
    if not taxonomy:
        raise HTTPException(status_code=404, detail="Taxonomy not found")
    return _taxonomy_to_response(taxonomy, term_count=len(taxonomy.terms or []))


@router.delete("/{taxonomy_id}", status_code=204)
async def delete_taxonomy(
    taxonomy_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Delete a taxonomy and all its terms and suggestions."""
    svc = TaxonomyService()
    deleted = await svc.delete_taxonomy(db, taxonomy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Taxonomy not found")


# ============================================================
# Term management
# ============================================================

@router.get("/{taxonomy_id}/terms", response_model=list[TermResponse])
async def list_terms(
    taxonomy_id: str,
    facet: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List terms for a taxonomy, optionally scoped to a facet."""
    svc = TaxonomyService()
    taxonomy = await svc.get_taxonomy(db, taxonomy_id)
    if not taxonomy:
        raise HTTPException(status_code=404, detail="Taxonomy not found")
    terms = taxonomy.terms or []
    if facet:
        terms = [t for t in terms if t.facet == facet]
    return [_term_to_response(t) for t in terms]


@router.post("/{taxonomy_id}/terms", response_model=TermResponse, status_code=201)
async def add_term(
    taxonomy_id: str,
    body: TermCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Add a term to a taxonomy facet."""
    svc = TaxonomyService()
    # Verify taxonomy exists
    if not await svc.get_taxonomy(db, taxonomy_id):
        raise HTTPException(status_code=404, detail="Taxonomy not found")
    try:
        terms = await svc.add_terms(db,
            taxonomy_id=taxonomy_id,
            terms=[{
                "facet": body.facet,
                "value": body.value,
                "keywords": body.keywords or [],
                "sort_order": body.sort_order or 0,
            }],
        )
        await db.commit()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not terms:
        raise HTTPException(status_code=500, detail="Failed to create term")
    return _term_to_response(terms[0])


@router.patch("/{taxonomy_id}/terms/{term_id}", response_model=TermResponse)
async def update_term(
    taxonomy_id: str,
    term_id: str,
    body: TermUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update a taxonomy term."""
    svc = TaxonomyService()
    term = await svc.update_term(db, 
        term_id,
        label=body.label,
        keywords=body.keywords,
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    return _term_to_response(term)


@router.delete("/{taxonomy_id}/terms/{term_id}", status_code=204)
async def delete_term(
    taxonomy_id: str,
    term_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Delete a taxonomy term."""
    svc = TaxonomyService()
    deleted = await svc.delete_term(db, term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Term not found")


# ============================================================
# Coverage analytics
# ============================================================

@router.get("/{taxonomy_id}/coverage")
async def get_coverage(
    taxonomy_id: str,
    source_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Coverage analytics: classified vs. unclassified, per-facet and per-term breakdowns."""
    # Verify taxonomy exists first
    svc = TaxonomyService()
    taxonomy = await svc.get_taxonomy(db, taxonomy_id)
    if not taxonomy:
        raise HTTPException(status_code=404, detail="Taxonomy not found")

    coverage_svc = TaxonomyCoverageService(db)
    return await coverage_svc.get_coverage(taxonomy_id, source_id=source_id)


# ============================================================
# Stale document detection
# ============================================================

@router.get("/{taxonomy_id}/stale", response_model=list[DocumentContentSummary])
async def list_stale_documents(
    taxonomy_id: str,
    source_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List documents classified with an outdated taxonomy version."""
    svc = TaxonomyService()
    if not await svc.get_taxonomy(db, taxonomy_id):
        raise HTTPException(status_code=404, detail="Taxonomy not found")

    coverage_svc = TaxonomyCoverageService(db)
    docs = await coverage_svc.get_stale_documents(taxonomy_id, source_id=source_id, limit=limit)
    return [_doc_to_summary(d) for d in docs]


@router.get("/{taxonomy_id}/stale/count")
async def count_stale_documents(
    taxonomy_id: str,
    source_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Count documents with outdated classifications."""
    svc = TaxonomyService()
    if not await svc.get_taxonomy(db, taxonomy_id):
        raise HTTPException(status_code=404, detail="Taxonomy not found")

    coverage_svc = TaxonomyCoverageService(db)
    count = await coverage_svc.count_stale(taxonomy_id, source_id=source_id)
    return {"count": count}


# ============================================================
# Suggestions
# ============================================================

@router.get("/{taxonomy_id}/suggestions", response_model=list[SuggestionResponse])
async def list_suggestions(
    taxonomy_id: str,
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List term suggestions for a taxonomy, sorted by frequency."""
    svc = TaxonomySuggestionService(db)
    suggestions = await svc.list_suggestions(taxonomy_id, status=status, limit=limit)
    return [_suggestion_to_response(s) for s in suggestions]


@router.post(
    "/{taxonomy_id}/suggestions/{suggestion_id}/approve",
    response_model=TermResponse,
)
async def approve_suggestion(
    taxonomy_id: str,
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Approve a suggestion: create the term in the taxonomy."""
    svc = TaxonomySuggestionService(db)
    try:
        term = await svc.approve_suggestion(suggestion_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not term:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return _term_to_response(term)


@router.post(
    "/{taxonomy_id}/suggestions/{suggestion_id}/reject",
    response_model=SuggestionResponse,
)
async def reject_suggestion(
    taxonomy_id: str,
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Reject a suggestion."""
    svc = TaxonomySuggestionService(db)
    try:
        suggestion = await svc.reject_suggestion(suggestion_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return _suggestion_to_response(suggestion)


@router.post(
    "/{taxonomy_id}/suggestions/{suggestion_id}/merge",
    response_model=SuggestionResponse,
)
async def merge_suggestion(
    taxonomy_id: str,
    suggestion_id: str,
    body: MergeRequest,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Merge suggestion into an existing term (adds it as a keyword alias)."""
    svc = TaxonomySuggestionService(db)
    try:
        suggestion = await svc.merge_suggestion(suggestion_id, merge_into_value=body.merge_into_value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return _suggestion_to_response(suggestion)
