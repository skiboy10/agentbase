"""
Search method selection for library discovery.

Picks the optimal search method (hybrid, vector, deep_search) based on
query characteristics. Pure heuristic — no LLM dependency.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.discovery.query_analyzer import QueryAnalysis


# Keywords that force specific methods
_COMPARISON_KEYWORDS = ["compare", "vs", "versus", "difference", "differences", "contrast"]
_SIMILARITY_KEYWORDS = ["similar", "like", "related", "analogous", "equivalent"]


def select_method(analysis: "QueryAnalysis") -> tuple[str, str]:
    """Select the best search method for a query.

    Args:
        analysis: QueryAnalysis from the query analyzer

    Returns:
        Tuple of (method, reason) where method is one of:
        'hybrid', 'vector', 'deep_search'
    """
    query_lower = analysis.original_query.lower()

    # Check for comparison keywords → deep_search
    for kw in _COMPARISON_KEYWORDS:
        if f" {kw} " in f" {query_lower} ":
            return ("deep_search", "Comparison query — decomposing into sub-queries for each side")

    # Check for similarity keywords → vector
    for kw in _SIMILARITY_KEYWORDS:
        if f" {kw} " in f" {query_lower} ":
            return ("vector", "Semantic similarity search — pure vector matching for best recall")

    # Route by complexity
    if analysis.query_complexity == "multi-faceted":
        return ("deep_search", "Multi-part question — decomposing into sub-queries")

    if analysis.query_complexity == "exploratory":
        return ("hybrid", "Broad exploration — hybrid balances semantic and keyword match")

    # Default: simple → hybrid
    return ("hybrid", "Direct factual query — hybrid search gives best precision")
