"""
Discovery service for library recommendation and search method selection.

Helps external agents find the right library and search strategy for their
queries using heuristic scoring (no LLM dependency).
"""
from app.services.discovery.query_analyzer import QueryAnalysis, analyze_query
from app.services.discovery.library_scorer import ScoredLibrary, score_libraries
from app.services.discovery.method_selector import select_method

__all__ = [
    "QueryAnalysis",
    "ScoredLibrary",
    "analyze_query",
    "score_libraries",
    "select_method",
]
