"""
Verification tests for the modular refactoring.

These tests ensure that the refactored modules maintain backward compatibility
and that all imports work correctly after splitting large files into packages.
"""
import pytest


def _route_paths(router_or_app) -> list[str]:
    """
    Collect full route paths from a FastAPI app or APIRouter.

    Older FastAPI versions flatten included routers into plain routes with a
    ``path`` attribute. Newer versions (fastapi >= 0.139) defer inclusion
    behind wrapper objects (``_IncludedRouter``) that expose the nested router
    via ``original_router`` and the mount prefix via ``include_context``.
    This helper walks both shapes so the assertions stay version-agnostic.
    """
    paths: list[str] = []

    def _walk(routes, prefix: str = "") -> None:
        for route in routes:
            if hasattr(route, "path"):
                paths.append(prefix + route.path)
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                inner_prefix = prefix + (getattr(ctx, "prefix", "") or "")
                _walk(inner.routes, inner_prefix)

    _walk(router_or_app.routes)
    return paths


class TestRAGServiceRefactoring:
    """Verify RAG service modular refactoring."""

    def test_main_import_works(self):
        """RAGService can be imported from main services module."""
        from app.services import RAGService, RAGContext, RAGSource, SearchResult
        assert RAGService is not None
        assert RAGContext is not None
        assert RAGSource is not None
        assert SearchResult is not None

    def test_package_import_works(self):
        """RAGService can be imported from rag package directly."""
        from app.services.rag import RAGService, RAGContext, RAGSource, SearchResult
        assert RAGService is not None

    def test_backward_compat_import_works(self):
        """RAGService can be imported from original rag_service.py."""
        from app.services.rag_service import RAGService, RAGContext, RAGSource, SearchResult
        assert RAGService is not None

    def test_imports_are_same_class(self):
        """All import paths resolve to the same class."""
        from app.services import RAGService as RS1
        from app.services.rag import RAGService as RS2
        from app.services.rag_service import RAGService as RS3
        assert RS1 is RS2
        assert RS2 is RS3

    def test_utility_functions_available(self):
        """Utility functions are exported correctly."""
        from app.services.rag import reciprocal_rank_fusion, weighted_rrf, get_qdrant_client
        assert callable(reciprocal_rank_fusion)
        assert callable(weighted_rrf)
        assert callable(get_qdrant_client)

    def test_submodule_imports_work(self):
        """Individual submodules can be imported."""
        from app.services.rag.types import SearchResult, RAGSource, RAGContext
        from app.services.rag.fusion import reciprocal_rank_fusion, weighted_rrf
        from app.services.rag.client import get_qdrant_client
        from app.services.rag.service import RAGService
        assert SearchResult is not None
        assert RAGService is not None


class TestProjectsRouterRefactoring:
    """Verify projects router modular refactoring."""

    def test_main_router_import(self):
        """Main router can be imported."""
        from app.api.projects import router
        assert router is not None

    def test_schemas_import(self):
        """Schemas can be imported from package."""
        from app.api.projects import (
            ProjectCreate,
            ProjectUpdate,
            ProjectResponse,
            KnowledgeSourceAssignment,
        )
        assert ProjectCreate is not None
        assert ProjectResponse is not None

    def test_submodule_routers_exist(self):
        """Sub-routers are accessible."""
        from app.api.projects.crud import router as crud_router
        from app.api.projects.knowledge import router as knowledge_router
        assert crud_router is not None
        assert knowledge_router is not None

    def test_router_has_expected_routes(self):
        """Main router has all expected routes combined."""
        from app.api.projects import router
        paths = _route_paths(router)

        # CRUD routes
        assert '/' in paths
        assert '/{project_id}' in paths

        # Knowledge routes
        assert '/{project_id}/knowledge-sources' in paths


class TestMainAppIntegration:
    """Verify the main app loads with refactored modules."""

    def test_main_app_loads(self):
        """Main app loads without import errors."""
        from app.main import app
        assert app is not None

    def test_project_routes_registered(self):
        """Project routes are registered in the main app."""
        from app.main import app
        paths = _route_paths(app)

        # Check that /api/projects routes exist
        project_paths = [p for p in paths if '/api/projects' in p]
        assert len(project_paths) > 0

    def test_health_endpoint_works(self):
        """Health endpoint is accessible."""
        from app.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200


class TestRRFFusion:
    """Test RRF fusion utilities work correctly."""

    def test_rrf_empty_lists(self):
        """RRF handles empty input."""
        from app.services.rag.fusion import reciprocal_rank_fusion
        result = reciprocal_rank_fusion([])
        assert result == []

    def test_rrf_single_list(self):
        """RRF returns single list unchanged."""
        from app.services.rag.fusion import reciprocal_rank_fusion
        from app.services.rag.types import SearchResult

        results = [
            SearchResult(content="a", source="s1", score=0.9, metadata={"content_hash": "h1"}),
            SearchResult(content="b", source="s2", score=0.8, metadata={"content_hash": "h2"}),
        ]
        merged = reciprocal_rank_fusion([results])
        assert len(merged) == 2
        assert merged[0].content == "a"

    def test_rrf_multiple_lists(self):
        """RRF merges multiple lists with RRF scoring."""
        from app.services.rag.fusion import reciprocal_rank_fusion
        from app.services.rag.types import SearchResult

        list1 = [
            SearchResult(content="a", source="s1", score=0.9, metadata={"content_hash": "h1"}),
            SearchResult(content="b", source="s2", score=0.8, metadata={"content_hash": "h2"}),
        ]
        list2 = [
            SearchResult(content="b", source="s2", score=0.95, metadata={"content_hash": "h2"}),
            SearchResult(content="c", source="s3", score=0.85, metadata={"content_hash": "h3"}),
        ]

        merged = reciprocal_rank_fusion([list1, list2])

        # "b" appears in both lists, should have higher combined score
        assert len(merged) == 3
        # Verify fusion_method is set
        assert merged[0].metadata.get("fusion_method") == "rrf"
