"""
Coverage gap analysis for libraries.

Queries taxonomy terms and counts chunks per term across all source
collections in the library to produce a structured coverage report.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.models import Library, Source, TaxonomyTerm
from app.services.ingestion.qdrant_client import get_qdrant_client

logger = structlog.get_logger()

# Coverage rating thresholds
DEEP_THRESHOLD = 20
ADEQUATE_THRESHOLD = 10
THIN_THRESHOLD = 1


def _rate_coverage(chunk_count: int) -> str:
    """Rate coverage depth based on chunk count."""
    if chunk_count >= DEEP_THRESHOLD:
        return "deep"
    elif chunk_count >= ADEQUATE_THRESHOLD:
        return "adequate"
    elif chunk_count >= THIN_THRESHOLD:
        return "thin"
    return "none"


def _total_points_in_collection(client, collection_name: str) -> int:
    """Get total point count for a collection, returning 0 on error."""
    try:
        info = client.get_collection(collection_name)
        return info.points_count or 0
    except Exception:
        return 0


def _scroll_collection_metadata(client, collection_name: str) -> list[dict]:
    """Scroll all points in a collection and return their metadata dicts."""
    all_metadata = []
    offset = None
    try:
        while True:
            points, next_offset = client.scroll(
                collection_name=collection_name,
                offset=offset,
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for p in points:
                meta = (p.payload or {}).get("metadata", {})
                if meta:
                    all_metadata.append(meta)
            offset = next_offset
            if offset is None:
                break
    except Exception as exc:
        logger.warning("Failed to scroll collection", collection=collection_name, error=str(exc))
    return all_metadata


def _facet_to_metadata_key(facet: str) -> str:
    """Convert a taxonomy facet name to the metadata key used by the enrichment pipeline.

    The enrichment pipeline stores classifications under "{facet}s"
    (e.g. "Content Type" → "Content Types", "Task" → "Tasks").
    Special case: "doc_categories" → "doc_category".
    """
    if facet == "doc_categories":
        return "doc_category"
    return f"{facet}s"


async def get_library_coverage(
    db: AsyncSession,
    library_id: str,
) -> dict:
    """Analyze taxonomy coverage for a library.

    Scrolls metadata from each source collection and counts chunks
    matching each taxonomy term. Works regardless of whether metadata
    keys contain special characters (spaces, slashes).

    Returns a structured report with per-term coverage ratings.
    """
    # Load library with sources eagerly loaded
    stmt = (
        select(Library)
        .options(selectinload(Library.sources))
        .where(Library.id == library_id)
    )
    result = await db.execute(stmt)
    library = result.scalar_one_or_none()
    if not library:
        return {"error": f"Library not found: {library_id}"}

    if not library.taxonomy_id:
        return {
            "library_id": library_id,
            "library_name": library.name,
            "error": "No taxonomy linked to this library. Link a taxonomy first via update_library.",
        }

    # Get taxonomy terms
    term_stmt = (
        select(TaxonomyTerm)
        .where(TaxonomyTerm.taxonomy_id == library.taxonomy_id)
        .order_by(TaxonomyTerm.facet, TaxonomyTerm.value)
    )
    term_result = await db.execute(term_stmt)
    terms = term_result.scalars().all()

    if not terms:
        return {
            "library_id": library_id,
            "library_name": library.name,
            "taxonomy_id": library.taxonomy_id,
            "error": "Taxonomy has no terms. Add terms first.",
        }

    # Collect source collection names
    source_collections = [
        s.collection_name for s in library.sources
        if s.collection_name and s.status == "indexed"
    ]

    try:
        client = get_qdrant_client()
    except Exception as e:
        return {
            "library_id": library_id,
            "library_name": library.name,
            "error": f"Cannot connect to Qdrant: {e}",
        }

    # Scroll all metadata from all source collections.
    # This avoids Qdrant's dot-notation filter limitation with keys
    # containing spaces or slashes (e.g. "Content Types", "System/Components").
    all_metadata: list[dict] = []
    for coll in source_collections:
        all_metadata.extend(_scroll_collection_metadata(client, coll))

    total_points = len(all_metadata)

    # Count chunks per taxonomy term
    coverage_items = []

    for term in terms:
        metadata_key = _facet_to_metadata_key(term.facet)

        chunk_count = 0
        for meta in all_metadata:
            value = meta.get(metadata_key)
            if isinstance(value, list) and term.value in value:
                chunk_count += 1
            elif isinstance(value, str) and value == term.value:
                chunk_count += 1

        percentage = round((chunk_count / total_points * 100), 1) if total_points > 0 else 0.0

        coverage_items.append({
            "facet": term.facet,
            "term": term.value,
            "chunk_count": chunk_count,
            "percentage": percentage,
            "rating": _rate_coverage(chunk_count),
        })

    # Summary stats
    ratings = [item["rating"] for item in coverage_items]
    summary = {
        "total_terms": len(terms),
        "total_chunks": total_points,
        "deep": ratings.count("deep"),
        "adequate": ratings.count("adequate"),
        "thin": ratings.count("thin"),
        "none": ratings.count("none"),
    }

    # Group by facet for readability
    facets: dict[str, list] = {}
    for item in coverage_items:
        facets.setdefault(item["facet"], []).append(item)

    return {
        "library_id": library_id,
        "library_name": library.name,
        "taxonomy_id": library.taxonomy_id,
        "summary": summary,
        "facets": facets,
        "items": coverage_items,
    }
