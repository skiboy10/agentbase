"""Tests for agentbase_discover_library and agentbase_search_library MCP tools."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"


class TestMethodSelector:
    """Test method_selector.select_method."""

    def test_simple_query_returns_hybrid(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="MeshRouter guest network",
            query_complexity="simple",
            token_count=3,
        )
        method, reason = select_method(analysis)
        assert method == "hybrid"

    def test_multifaceted_returns_deep_search(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="VLAN setup and firewall rules",
            query_complexity="multi-faceted",
            token_count=6,
        )
        method, reason = select_method(analysis)
        assert method == "deep_search"

    def test_exploratory_returns_hybrid(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="how does VLAN isolation work",
            query_complexity="exploratory",
            token_count=5,
        )
        method, reason = select_method(analysis)
        assert method == "hybrid"

    def test_compare_keyword_forces_deep_search(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="compare MeshRouter and pfRoute",
            query_complexity="simple",
            token_count=4,
        )
        method, reason = select_method(analysis)
        assert method == "deep_search"

    def test_vs_keyword_forces_deep_search(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="MeshRouter vs pfRoute",
            query_complexity="simple",
            token_count=3,
        )
        method, reason = select_method(analysis)
        assert method == "deep_search"

    def test_similar_keyword_forces_vector(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="find similar configurations",
            query_complexity="simple",
            token_count=3,
        )
        method, reason = select_method(analysis)
        assert method == "vector"

    def test_related_keyword_forces_vector(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        analysis = QueryAnalysis(
            original_query="show related network topics",
            query_complexity="simple",
            token_count=4,
        )
        method, reason = select_method(analysis)
        assert method == "vector"

    def test_reason_always_non_empty(self):
        from app.services.discovery.query_analyzer import QueryAnalysis
        from app.services.discovery.method_selector import select_method
        for complexity in ["simple", "multi-faceted", "exploratory"]:
            analysis = QueryAnalysis(
                original_query="test query",
                query_complexity=complexity,
                token_count=2,
            )
            _, reason = select_method(analysis)
            assert len(reason) > 0


class TestDiscoverLibraryTool:
    """Test agentbase_discover_library MCP tool with mocked services."""

    @pytest.mark.asyncio
    async def test_discover_returns_recommendations(self):
        from app.mcp.tools.discovery import agentbase_discover_library

        # Mock taxonomy service
        mock_tax_svc = MagicMock()
        mock_tax_svc.list_taxonomies = AsyncMock(return_value=[])
        mock_tax_svc.get_taxonomy = AsyncMock(return_value=None)

        # Mock library service
        mock_lib = MagicMock()
        mock_lib.id = "lib-1"
        mock_lib.name = "MeshRouter Network Guide"
        mock_lib.description = "Complete MeshRouter documentation"
        mock_lib.taxonomy_id = None
        mock_lib.chunk_count = 500
        mock_lib.source_count = 3
        mock_lib.sources = []

        mock_lib_svc = MagicMock()
        mock_lib_svc.list_kbs = AsyncMock(return_value=[mock_lib])

        with patch("app.mcp.tools.discovery.async_session_maker") as mock_maker, \
             patch("app.services.taxonomy.TaxonomyService", return_value=mock_tax_svc), \
             patch("app.services.library.LibraryService", return_value=mock_lib_svc):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await agentbase_discover_library("MeshRouter guest network")
            assert "recommendations" in result
            assert "query_analysis" in result
            assert result["recommendation_count"] >= 0

    @pytest.mark.asyncio
    async def test_discover_empty_libraries(self):
        from app.mcp.tools.discovery import agentbase_discover_library

        mock_tax_svc = MagicMock()
        mock_tax_svc.list_taxonomies = AsyncMock(return_value=[])

        mock_lib_svc = MagicMock()
        mock_lib_svc.list_kbs = AsyncMock(return_value=[])

        with patch("app.mcp.tools.discovery.async_session_maker") as mock_maker, \
             patch("app.services.taxonomy.TaxonomyService", return_value=mock_tax_svc), \
             patch("app.services.library.LibraryService", return_value=mock_lib_svc):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await agentbase_discover_library("anything")
            assert result["recommendations"] == []
            assert result["recommendation_count"] == 0


class TestSearchLibraryTool:
    """Test agentbase_search_library MCP tool with mocked services."""

    @pytest.mark.asyncio
    async def test_invalid_method(self):
        from app.mcp.tools.discovery import agentbase_search_library

        with patch("app.mcp.tools.discovery.async_session_maker"):
            result = await agentbase_search_library(
                query="test",
                library_id="lib-1",
                method="invalid_method",
            )
            assert "error" in result
            assert "invalid" in result["error"].lower() or "Invalid" in result["error"]

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from app.mcp.tools.discovery import agentbase_search_library
        from app.services.rag.types import SearchResult

        mock_results = [
            SearchResult(
                content="Test content about MeshRouter",
                source="https://example.com/doc1",
                score=0.95,
                metadata={"platforms": ["MeshRouter"]},
                title="MeshRouter Guide",
                source_name="MeshRouter Docs",
                document_path="/docs/meshrouter.md",
                collection="test_collection",
            ),
        ]

        mock_rag = MagicMock()
        mock_rag.search_hybrid = AsyncMock(return_value=mock_results)

        with patch("app.mcp.tools.discovery.async_session_maker") as mock_maker, \
             patch("app.services.rag.service.RAGService", return_value=mock_rag):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await agentbase_search_library(
                query="MeshRouter guest network",
                library_id="lib-1",
                method="hybrid",
            )
            assert "results" in result
            assert result["result_count"] == 1
            assert result["method_used"] == "hybrid"
            assert "refinement_hints" in result

    @pytest.mark.asyncio
    async def test_auto_method_selection(self):
        from app.mcp.tools.discovery import agentbase_search_library

        mock_rag = MagicMock()
        mock_rag.search_hybrid = AsyncMock(return_value=[])

        with patch("app.mcp.tools.discovery.async_session_maker") as mock_maker, \
             patch("app.services.rag.service.RAGService", return_value=mock_rag):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await agentbase_search_library(
                query="simple test query",
                library_id="lib-1",
                method="auto",
            )
            assert result["method_used"] in ("hybrid", "vector", "deep_search")
            assert len(result["method_reason"]) > 0
