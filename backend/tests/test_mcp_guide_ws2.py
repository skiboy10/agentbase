"""
Tests for WS2 MCP tool enhancements — guide workflows, agentbase_list_stale_sources,
agentbase_get_library_coverage tools.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"


class TestGuideWS2Workflows:
    """Test that new WS2 workflows are present and functional."""

    @pytest.mark.asyncio
    async def test_coverage_keyword_match(self):
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("check coverage gaps in my library")
        assert "workflow" in result
        assert "coverage" in result["workflow"]["title"].lower()

    @pytest.mark.asyncio
    async def test_maintain_keyword_match(self):
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("maintain and refresh my library")
        assert "workflow" in result
        assert "maintain" in result["workflow"]["title"].lower()

    @pytest.mark.asyncio
    async def test_stale_keyword_match(self):
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("find stale sources that need updating")
        assert "workflow" in result

    @pytest.mark.asyncio
    async def test_exact_key_assess_coverage(self):
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("assess_coverage")
        assert "workflow" in result
        assert result["matched_by"] == "exact_key"

    @pytest.mark.asyncio
    async def test_exact_key_maintain_library(self):
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("maintain_library")
        assert "workflow" in result
        assert result["matched_by"] == "exact_key"


class TestListStaleSourcesTool:
    """Test the agentbase_list_stale_sources MCP tool."""

    @pytest.mark.asyncio
    @patch("app.mcp.tools.source_ops.async_session_maker")
    async def test_returns_list(self, mock_session_maker):
        from app.mcp.tools.source_ops import agentbase_list_stale_sources

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_db
        mock_ctx.__aexit__.return_value = None
        mock_session_maker.return_value = mock_ctx

        result = await agentbase_list_stale_sources()
        assert isinstance(result, dict)
        assert "items" in result
        assert isinstance(result["items"], list)
        assert "total" in result
        assert "has_more" in result


class TestGetLibraryCoverageTool:
    """Test the agentbase_get_library_coverage MCP tool."""

    @pytest.mark.asyncio
    @patch("app.mcp.tools.source_ops.async_session_maker")
    async def test_returns_error_for_missing_library(self, mock_session_maker):
        from app.mcp.tools.source_ops import agentbase_get_library_coverage

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_db
        mock_ctx.__aexit__.return_value = None
        mock_session_maker.return_value = mock_ctx

        result = await agentbase_get_library_coverage("nonexistent")
        assert "error" in result
