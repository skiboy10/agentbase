"""
MCP Tools for Taxonomy Management

Provides tools for managing classification taxonomies:
- Taxonomy CRUD
- Term management (add, update, delete)
- Taxonomy coverage analytics
- Suggestion review (approve, reject, merge)
"""

from typing import Optional
import structlog

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.core.auth import Scope, check_mcp_scope

logger = structlog.get_logger()


def _taxonomy_to_dict(taxonomy, term_count: int = 0) -> dict:
    """Convert Taxonomy ORM model to dict.

    Caller must pass term_count explicitly — never access taxonomy.terms here,
    since this dict is built outside the path that eager-loads the relationship.
    """
    return {
        "id": taxonomy.id,
        "name": taxonomy.name,
        "description": taxonomy.description,
        "project_id": getattr(taxonomy, "project_id", None),
        "version": getattr(taxonomy, "version", 1),
        "term_count": term_count,
        "created_at": taxonomy.created_at.isoformat() if taxonomy.created_at else None,
        "updated_at": taxonomy.updated_at.isoformat() if taxonomy.updated_at else None,
    }


def _term_to_dict(term) -> dict:
    """Convert TaxonomyTerm ORM model to dict."""
    return {
        "id": term.id,
        "taxonomy_id": term.taxonomy_id,
        "facet": term.facet,
        "value": term.value,
        "parent_value": getattr(term, "parent_value", None),
        "keywords": term.keywords or [],
        "sort_order": term.sort_order or 0,
        "created_at": term.created_at.isoformat() if term.created_at else None,
    }


def _suggestion_to_dict(sug) -> dict:
    """Convert TaxonomySuggestion ORM model to dict."""
    return {
        "id": sug.id,
        "taxonomy_id": sug.taxonomy_id,
        "facet": sug.facet,
        "suggested_value": sug.suggested_value,
        "frequency": sug.frequency,
        "sample_document_ids": sug.sample_document_ids,
        "status": sug.status,
        "merged_into": sug.merged_into,
        "created_at": sug.created_at.isoformat() if sug.created_at else None,
        "reviewed_at": sug.reviewed_at.isoformat() if sug.reviewed_at else None,
    }


# ============================================================
# Taxonomy CRUD
# ============================================================

@mcp.tool(
    description="List all taxonomies with pagination. Optional project_id filter.",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_taxonomies(project_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    """List all taxonomies with pagination."""
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            rows = await svc.list_taxonomies(db, project_id=project_id)
            total = len(rows)
            page = rows[offset:offset + limit]
            items = [_taxonomy_to_dict(t, count) for t, count in page]
            return {
                "total": total,
                "count": len(items),
                "offset": offset,
                "has_more": offset + len(items) < total,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "items": items,
            }
        except Exception as e:
            return {"error": f"Failed to list taxonomies: {str(e)}"}


@mcp.tool(
    description="Get a taxonomy by ID with its full term list.",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_get_taxonomy(taxonomy_id: str) -> dict:
    """Get taxonomy details with terms."""
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            taxonomy = await svc.get_taxonomy(db, taxonomy_id)
            if not taxonomy:
                return {"error": f"Taxonomy not found: {taxonomy_id}"}
            terms = taxonomy.terms or []
            result = _taxonomy_to_dict(taxonomy, term_count=len(terms))
            result["terms"] = [_term_to_dict(t) for t in terms]
            return result
        except Exception as e:
            return {"error": f"Failed to get taxonomy: {str(e)}"}


@mcp.tool(
    description=(
        "Create a taxonomy for content classification. "
        "After creation, add terms with agentbase_add_taxonomy_term, then link to a library."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_create_taxonomy(
    name: str,
    description: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    """Create a taxonomy."""
    check_mcp_scope(Scope.WRITE)
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            taxonomy = await svc.create_taxonomy(db, name=name, description=description, project_id=project_id)
            await db.commit()
            await db.refresh(taxonomy)
            logger.info("MCP: Created taxonomy", taxonomy_id=taxonomy.id, name=name)
            return _taxonomy_to_dict(taxonomy, term_count=0)
        except Exception as e:
            return {"error": f"Failed to create taxonomy: {str(e)}"}


@mcp.tool(
    description="Delete a taxonomy and all its terms and suggestions. Irreversible.",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_delete_taxonomy(taxonomy_id: str) -> dict:
    """Delete a taxonomy."""
    check_mcp_scope(Scope.WRITE)
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            taxonomy = await svc.get_taxonomy(db, taxonomy_id)
            if not taxonomy:
                return {"error": f"Taxonomy not found: {taxonomy_id}"}
            await svc.delete_taxonomy(db, taxonomy_id)
            await db.commit()
            logger.info("MCP: Deleted taxonomy", taxonomy_id=taxonomy_id)
            return {"status": "deleted", "id": taxonomy_id}
        except Exception as e:
            return {"error": f"Failed to delete taxonomy: {str(e)}"}


# ============================================================
# Term Management
# ============================================================

@mcp.tool(
    description="List terms in a taxonomy with pagination. Optional facet filter (e.g., 'platform').",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_taxonomy_terms(
    taxonomy_id: str,
    facet: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List taxonomy terms with pagination."""
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            taxonomy = await svc.get_taxonomy(db, taxonomy_id)
            if not taxonomy:
                return {"error": f"Taxonomy not found: {taxonomy_id}"}
            terms = taxonomy.terms or []
            if facet:
                terms = [t for t in terms if t.facet == facet]
            total = len(terms)
            page = terms[offset:offset + limit]
            items = [_term_to_dict(t) for t in page]
            return {
                "total": total,
                "count": len(items),
                "offset": offset,
                "has_more": offset + len(items) < total,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "items": items,
            }
        except Exception as e:
            return {"error": f"Failed to list terms: {str(e)}"}


@mcp.tool(
    description=(
        "Add a term to a taxonomy facet. "
        "keywords help auto-classification (e.g., facet='platform', value='AcmeCRM', keywords=['acmecrm'])."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_add_taxonomy_term(
    taxonomy_id: str,
    facet: str,
    value: str,
    keywords: Optional[list[str]] = None,
    sort_order: int = 0,
) -> dict:
    """Add a term to a taxonomy."""
    check_mcp_scope(Scope.WRITE)
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            taxonomy = await svc.get_taxonomy(db, taxonomy_id)
            if not taxonomy:
                return {"error": f"Taxonomy not found: {taxonomy_id}"}

            terms = await svc.add_terms(db, taxonomy_id=taxonomy_id, terms=[{
                "facet": facet,
                "value": value,
                "keywords": keywords or [],
                "sort_order": sort_order,
            }])
            await db.commit()

            if not terms:
                return {"error": "Failed to create term"}

            logger.info("MCP: Added taxonomy term", taxonomy_id=taxonomy_id, facet=facet, value=value)
            return _term_to_dict(terms[0])
        except Exception as e:
            return {"error": f"Failed to add term: {str(e)}"}


@mcp.tool(
    description="Delete a term from a taxonomy.",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_delete_taxonomy_term(
    taxonomy_id: str,
    term_id: str,
) -> dict:
    """Delete a taxonomy term."""
    check_mcp_scope(Scope.WRITE)
    from app.services.taxonomy import TaxonomyService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            # Verify taxonomy exists
            taxonomy = await svc.get_taxonomy(db, taxonomy_id)
            if not taxonomy:
                return {"error": f"Taxonomy not found: {taxonomy_id}"}

            await svc.delete_term(db, term_id)
            await db.commit()
            logger.info("MCP: Deleted taxonomy term", taxonomy_id=taxonomy_id, term_id=term_id)
            return {"status": "deleted", "id": term_id}
        except Exception as e:
            return {"error": f"Failed to delete term: {str(e)}"}


# ============================================================
# Taxonomy Suggestions
# ============================================================

@mcp.tool(
    description=(
        "List term suggestions for a taxonomy with pagination (new terms detected during enrichment). "
        "Review with agentbase_approve_taxonomy_suggestion or agentbase_reject_taxonomy_suggestion."
    ),
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_list_taxonomy_suggestions(
    taxonomy_id: str,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List taxonomy suggestions with pagination. Sorted by frequency."""
    from app.services.taxonomy import TaxonomySuggestionService

    fetch_limit = min(limit + offset, 200)
    async with async_session_maker() as db:
        try:
            svc = TaxonomySuggestionService(db)
            suggestions = await svc.list_suggestions(taxonomy_id, status=status, limit=fetch_limit)
            total = len(suggestions)
            page = suggestions[offset:offset + limit]
            items = [_suggestion_to_dict(s) for s in page]
            return {
                "total": total,
                "count": len(items),
                "offset": offset,
                "has_more": offset + len(items) < total,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "items": items,
            }
        except Exception as e:
            return {"error": f"Failed to list suggestions: {str(e)}"}


@mcp.tool(
    description="Approve a suggestion, creating it as a new term in the taxonomy.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_approve_taxonomy_suggestion(
    taxonomy_id: str,
    suggestion_id: str,
) -> dict:
    """Approve a suggestion → creates a new term."""
    check_mcp_scope(Scope.WRITE)
    from app.services.taxonomy import TaxonomySuggestionService

    async with async_session_maker() as db:
        try:
            svc = TaxonomySuggestionService(db)
            term = await svc.approve_suggestion(suggestion_id)
            if not term:
                return {"error": f"Suggestion not found: {suggestion_id}"}
            logger.info("MCP: Approved taxonomy suggestion", suggestion_id=suggestion_id)
            return _term_to_dict(term)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Failed to approve suggestion: {str(e)}"}


@mcp.tool(
    description="Reject a taxonomy suggestion without creating a term.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_reject_taxonomy_suggestion(
    taxonomy_id: str,
    suggestion_id: str,
) -> dict:
    """Reject a suggestion."""
    check_mcp_scope(Scope.WRITE)
    from app.services.taxonomy import TaxonomySuggestionService

    async with async_session_maker() as db:
        try:
            svc = TaxonomySuggestionService(db)
            suggestion = await svc.reject_suggestion(suggestion_id)
            if not suggestion:
                return {"error": f"Suggestion not found: {suggestion_id}"}
            logger.info("MCP: Rejected taxonomy suggestion", suggestion_id=suggestion_id)
            return _suggestion_to_dict(suggestion)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Failed to reject suggestion: {str(e)}"}


# ============================================================
# Coverage Analytics
# ============================================================

@mcp.tool(
    description="Get classification coverage for a taxonomy — documents classified vs total, per-facet coverage, term usage, source count.",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_get_taxonomy_coverage(
    taxonomy_id: str,
) -> dict:
    """Get coverage statistics for a taxonomy."""
    from sqlalchemy import select, func
    from app.models import Source
    from app.services.taxonomy import TaxonomyService
    from app.services.taxonomy.analytics import TaxonomyCoverageService

    async with async_session_maker() as db:
        try:
            svc = TaxonomyService()
            taxonomy = await svc.get_taxonomy(db, taxonomy_id)
            if not taxonomy:
                return {"error": f"Taxonomy not found: {taxonomy_id}"}

            coverage = await TaxonomyCoverageService(db).get_coverage(taxonomy_id)

            stmt = select(func.count(Source.id)).where(
                Source.enrichment_enabled.is_(True),
                Source.enrichment_taxonomy_id == taxonomy_id,
            )
            result = await db.execute(stmt)
            source_count = int(result.scalar() or 0)

            return {
                "taxonomy_id": taxonomy_id,
                "taxonomy_name": taxonomy.name,
                **coverage,
                "source_count": source_count,
            }
        except Exception as e:
            return {"error": f"Failed to get coverage: {str(e)}"}
