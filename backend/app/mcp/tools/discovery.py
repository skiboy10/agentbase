"""
MCP Tools for Library Discovery and Search

Enables external AI agents to efficiently discover the best knowledge library
for their queries and search within it using the optimal strategy.
"""
from typing import Optional
import structlog

from app.mcp.server import mcp
from app.core.database import async_session_maker

logger = structlog.get_logger()

# Maximum chars per chunk content before truncation kicks in
_MAX_RESPONSE_CHARS = 16000
_MAX_CHUNK_CONTENT = 500
_MAX_FILTER_VALUES = 10


@mcp.tool(
    description=(
        "Find the best knowledge library for a query. Returns ranked recommendations "
        "with confidence scores, coverage highlights, and recommended search methods. "
        "Call this first when you need domain knowledge, then use agentbase_search_library with "
        "the returned library_id."
    ),
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def agentbase_discover_library(query: str, top_k: int = 3) -> dict:
    """Discover the best library for a query.

    Returns:
        dict with keys:
            query_analysis (dict) - detected entities, complexity, domain signals
            recommendations (list[dict]) - ranked libraries, each with:
                library_id (str), library_name (str), confidence (float),
                description (str|None), coverage_highlights (list[dict]),
                recommended_method (str), method_reason (str),
                chunk_count (int), source_count (int)
            recommendation_count (int) - number of recommendations returned
        On error: {"error": str}
    """
    from app.services.discovery import analyze_query, score_libraries, select_method
    from app.services.library import LibraryService
    from app.services.library.coverage import get_library_coverage as _get_library_coverage
    from app.services.taxonomy import TaxonomyService

    top_k = max(1, min(top_k, 10))

    async with async_session_maker() as db:
        try:
            # Load taxonomy vocabulary for domain detection
            taxonomy_svc = TaxonomyService()
            all_taxonomies = await taxonomy_svc.list_taxonomies(db)
            taxonomy_vocab: dict[str, list[str]] = {}
            taxonomy_terms_by_library: dict[str, list[dict]] = {}

            for tax, _term_count in all_taxonomies:
                tax_detail = await taxonomy_svc.get_taxonomy(db, tax.id)
                if tax_detail and tax_detail.terms:
                    for term in tax_detail.terms:
                        facet = term.facet
                        if facet not in taxonomy_vocab:
                            taxonomy_vocab[facet] = []
                        if term.value not in taxonomy_vocab[facet]:
                            taxonomy_vocab[facet].append(term.value)

            # Analyze the query
            analysis = analyze_query(query, taxonomy_vocab=taxonomy_vocab)

            # Fetch all libraries
            lib_svc = LibraryService(db)
            all_libs = await lib_svc.list_kbs()
            if not all_libs:
                return {
                    "query_analysis": _analysis_to_dict(analysis),
                    "recommendations": [],
                    "recommendation_count": 0,
                }

            # Build library dicts and collect taxonomy terms per library
            lib_dicts = []
            for lib in all_libs:
                lib_dict = {
                    "id": lib.id,
                    "name": lib.name,
                    "description": lib.description,
                    "taxonomy_id": lib.taxonomy_id,
                    "chunk_count": lib.chunk_count or 0,
                    "source_count": lib.source_count or 0,
                }
                lib_dicts.append(lib_dict)

                # Load taxonomy terms for this library if it has a taxonomy
                if lib.taxonomy_id and lib.taxonomy_id not in taxonomy_terms_by_library:
                    tax_detail = await taxonomy_svc.get_taxonomy(db, lib.taxonomy_id)
                    if tax_detail and tax_detail.terms:
                        taxonomy_terms_by_library[lib.id] = [
                            {"value": t.value, "keywords": t.keywords}
                            for t in tax_detail.terms
                        ]

            # Score libraries
            scored = score_libraries(
                analysis.key_entities,
                lib_dicts,
                taxonomy_terms_by_library=taxonomy_terms_by_library,
            )

            # Build recommendations for top_k
            recommendations = []
            for sl in scored[:top_k]:
                # Get coverage highlights (top 5 terms only)
                coverage_highlights = []
                try:
                    if sl.taxonomy_id:
                        coverage = await _get_library_coverage(db, sl.library_id)
                        if coverage and "items" in coverage:
                            # Take top 5 by chunk_count
                            sorted_items = sorted(
                                coverage["items"],
                                key=lambda x: x.get("chunk_count", 0),
                                reverse=True,
                            )
                            coverage_highlights = [
                                {
                                    "facet": item["facet"],
                                    "term": item["term"],
                                    "chunk_count": item["chunk_count"],
                                    "rating": item["rating"],
                                }
                                for item in sorted_items[:5]
                            ]
                except Exception:
                    pass  # Coverage is best-effort

                # Select method for this recommendation
                method, reason = select_method(analysis)

                recommendations.append({
                    "library_id": sl.library_id,
                    "library_name": sl.library_name,
                    "confidence": sl.score,
                    "description": sl.description,
                    "score_breakdown": sl.score_breakdown,
                    "coverage_highlights": coverage_highlights,
                    "recommended_method": method,
                    "method_reason": reason,
                    "chunk_count": sl.chunk_count,
                    "source_count": sl.source_count,
                })

            logger.info(
                "MCP: agentbase_discover_library",
                query=query[:50],
                recommendations=len(recommendations),
            )

            return {
                "query_analysis": _analysis_to_dict(analysis),
                "recommendations": recommendations,
                "recommendation_count": len(recommendations),
            }

        except Exception as e:
            return {"error": f"Discovery failed: {str(e)}"}


@mcp.tool(
    description=(
        "Search a specific knowledge library. Use library_id from agentbase_discover_library. "
        "Set method='auto' to let the system choose the best search strategy, "
        "or specify 'hybrid', 'vector', or 'deep_search' directly."
    ),
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def agentbase_search_library(
    query: str,
    library_id: str,
    method: str = "auto",
    top_k: int = 5,
    filters: Optional[dict] = None,
    rerank: bool = True,
    include_context: bool = False,
    include_sources: bool = True,
) -> dict:
    """Search within a specific knowledge library.

    Returns:
        dict with keys:
            results (list[dict]) - search results, each with:
                content (str), source (str), score (float),
                title (str), source_name (str), metadata (dict)
            method_used (str) - actual search method used
            method_reason (str) - why this method was chosen
            result_count (int) - number of results returned
            truncated (bool) - whether content was truncated for size
            refinement_hints (dict) - available_filters (dict), suggested_followup (str|None)
        On error: {"error": str}
    """
    from app.services.discovery import analyze_query, select_method
    from app.services.rag.service import RAGService

    top_k = max(1, min(top_k, 50))
    valid_methods = {"auto", "hybrid", "vector", "deep_search"}
    if method not in valid_methods:
        return {"error": f"Invalid method '{method}'. Must be one of: {', '.join(sorted(valid_methods))}"}

    async with async_session_maker() as db:
        try:
            rag = RAGService(db)

            # Resolve method if auto
            method_used = method
            method_reason = "User specified"
            if method == "auto":
                analysis = analyze_query(query)
                method_used, method_reason = select_method(analysis)

            # Execute search
            truncated = False
            stats = None

            if method_used == "deep_search":
                result = await rag.deep_search(
                    query=query,
                    knowledge_base_id=library_id,
                    top_k=top_k,
                    filters=filters,
                    rerank=rerank,
                    include_decomposition=False,
                )
                raw_results = result.results
                stats = result.stats
            elif method_used == "vector":
                raw_results = await rag.search_hybrid(
                    query=query,
                    knowledge_base_id=library_id,
                    top_k=top_k,
                    vector_weight=1.0,
                    filters=filters,
                    rerank=rerank,
                )
            else:
                # hybrid (default)
                raw_results = await rag.search_hybrid(
                    query=query,
                    knowledge_base_id=library_id,
                    top_k=top_k,
                    filters=filters,
                    rerank=rerank,
                )

            # Convert results to dicts with size guardrails
            results = []
            total_chars = 0
            for r in raw_results:
                content = r.content
                # Apply truncation if total response would exceed budget
                if total_chars + len(content) > _MAX_RESPONSE_CHARS:
                    content = content[:_MAX_CHUNK_CONTENT]
                    truncated = True
                total_chars += len(content)

                result_dict = {
                    "content": content,
                    "source": r.source,
                    "score": round(r.score, 4),
                    "title": r.title,
                    "source_name": r.source_name,
                }

                if include_sources:
                    result_dict["document_path"] = r.document_path
                    result_dict["collection"] = r.collection

                if r.rerank_score is not None:
                    result_dict["rerank_score"] = round(r.rerank_score, 4)

                # Include metadata but strip internal fields
                if r.metadata:
                    clean_meta = {
                        k: v for k, v in r.metadata.items()
                        if not k.startswith("_") and k not in ("content_hash", "embedding_model")
                    }
                    result_dict["metadata"] = clean_meta

                results.append(result_dict)

            # Build refinement hints from result metadata
            refinement_hints = _build_refinement_hints(raw_results)

            response = {
                "results": results,
                "method_used": method_used,
                "method_reason": method_reason,
                "result_count": len(results),
                "truncated": truncated,
                "refinement_hints": refinement_hints,
            }

            if stats:
                response["search_stats"] = stats

            logger.info(
                "MCP: agentbase_search_library",
                query=query[:50],
                library_id=library_id,
                method=method_used,
                results=len(results),
            )

            return response

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}


def _analysis_to_dict(analysis) -> dict:
    """Convert QueryAnalysis to a plain dict."""
    return {
        "original_query": analysis.original_query,
        "key_entities": analysis.key_entities,
        "query_complexity": analysis.query_complexity,
        "detected_domain": analysis.detected_domain,
        "domain_confidence": analysis.domain_confidence,
        "suggested_method": analysis.suggested_method,
        "token_count": analysis.token_count,
    }


def _build_refinement_hints(results) -> dict:
    """Extract refinement hints from search results."""
    available_filters: dict[str, list[str]] = {}
    source_names: set[str] = set()

    for r in results:
        if r.source_name:
            source_names.add(r.source_name)
        if r.metadata:
            for key in ("platforms", "products", "topics", "doc_category"):
                values = r.metadata.get(key)
                if values:
                    if key not in available_filters:
                        available_filters[key] = []
                    if isinstance(values, list):
                        for v in values:
                            if v not in available_filters[key]:
                                available_filters[key].append(v)
                    elif isinstance(values, str) and values not in available_filters[key]:
                        available_filters[key].append(values)

    # Cap filter values at _MAX_FILTER_VALUES
    for key in available_filters:
        available_filters[key] = available_filters[key][:_MAX_FILTER_VALUES]

    # Generate suggested followup if results are broad
    suggested_followup = None
    if len(source_names) > 3:
        suggested_followup = (
            f"Results span {len(source_names)} sources. "
            "Consider narrowing with filters or a more specific query."
        )
    elif available_filters and len(available_filters) > 1:
        filter_names = ", ".join(available_filters.keys())
        suggested_followup = f"Refine results using available filters: {filter_names}"

    return {
        "available_filters": available_filters,
        "suggested_followup": suggested_followup,
    }
