"""
Tests for MCP tool layer.

Tests tool registration, the guide tool, parameter handling, and
response shapes. Service layer is mocked — these test the MCP layer only.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before importing app
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"


# ============================================================
# Tool Registration
# ============================================================

class TestToolRegistration:
    """Verify all expected tools are registered on the FastMCP server."""

    def test_all_tools_registered(self):
        """All tools (original + guide + WS2 freshness/coverage) should be registered."""
        from app.mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert len(tools) >= 64, (
            f"Expected at least 64 tools, got {len(tools)}. "
            f"Registered: {sorted(tools.keys())}"
        )

    def test_all_tool_names_have_service_prefix(self):
        """Every registered tool name must start with 'agentbase_'.

        MCP best practice: service-prefixed tool names prevent collisions
        in multi-server environments (#85). This guards against future
        tools being added without the prefix.
        """
        from app.mcp.server import mcp

        tools = mcp._tool_manager._tools
        unprefixed = [name for name in tools if not name.startswith("agentbase_")]
        assert not unprefixed, (
            f"Tools missing the 'agentbase_' prefix: {sorted(unprefixed)}"
        )

    def test_expected_tool_names_present(self):
        """Key tools from each domain should be present."""
        from app.mcp.server import mcp

        tools = mcp._tool_manager._tools
        expected = [
            # auth
            "agentbase_bootstrap_api_key",
            # projects (deprecated)
            "agentbase_list_projects", "agentbase_get_project", "agentbase_create_project",
            # agents
            "agentbase_list_agents", "agentbase_get_agent", "agentbase_create_agent", "agentbase_update_agent",
            "agentbase_delete_agent", "agentbase_bind_knowledge_to_agent", "agentbase_bind_knowledge_base",
            "agentbase_unbind_knowledge_base", "agentbase_list_agent_knowledge_bases",
            # libraries
            "agentbase_list_libraries", "agentbase_get_library", "agentbase_create_library", "agentbase_update_library",
            "agentbase_delete_library", "agentbase_add_source_to_library", "agentbase_remove_source_from_library",
            "agentbase_recalculate_library_stats",
            # sources
            "agentbase_list_sources", "agentbase_get_source", "agentbase_create_source", "agentbase_delete_source",
            "agentbase_index_source", "agentbase_get_source_status", "agentbase_search_sources", "agentbase_deep_search",
            "agentbase_list_filter_values", "agentbase_list_filter_fields", "agentbase_upload_source_file",
            "agentbase_upload_source_files", "agentbase_add_files_to_source",
            "agentbase_get_full_document", "agentbase_delete_document", "agentbase_export_source_chunks",
            "agentbase_get_indexing_queue",
            # source_ops
            "agentbase_get_source_analytics", "agentbase_refresh_source", "agentbase_re_enrich_source",
            "agentbase_retry_failed_urls", "agentbase_get_watcher_statuses", "agentbase_get_watcher_status",
            "agentbase_start_watcher", "agentbase_stop_watcher", "agentbase_force_sync_watcher",
            "agentbase_list_stale_sources", "agentbase_get_library_coverage",
            # taxonomy
            "agentbase_list_taxonomies", "agentbase_get_taxonomy", "agentbase_create_taxonomy", "agentbase_delete_taxonomy",
            "agentbase_list_taxonomy_terms", "agentbase_add_taxonomy_term", "agentbase_delete_taxonomy_term",
            "agentbase_list_taxonomy_suggestions", "agentbase_approve_taxonomy_suggestion",
            "agentbase_reject_taxonomy_suggestion", "agentbase_get_taxonomy_coverage",
            # guide
            "agentbase_get_workflow_guide",
            # discovery
            "agentbase_discover_library", "agentbase_search_library",
            # evaluation
            "agentbase_list_question_sets", "agentbase_get_question_set", "agentbase_create_question_set",
            "agentbase_generate_questions", "agentbase_add_question", "agentbase_update_question",
            "agentbase_delete_question",
            # evaluation — experiments (slice 3)
            "agentbase_create_experiment", "agentbase_list_experiments", "agentbase_get_experiment",
            "agentbase_compare_experiment", "agentbase_get_comparison", "agentbase_promote_experiment",
            "agentbase_delete_experiment",
        ]
        missing = [name for name in expected if name not in tools]
        assert not missing, f"Missing tools: {missing}"

    def test_deprecated_tools_marked(self):
        """Project tools should have [DEPRECATED] in their descriptions."""
        from app.mcp.server import mcp

        tools = mcp._tool_manager._tools
        for name in ["agentbase_list_projects", "agentbase_get_project", "agentbase_create_project"]:
            tool = tools[name]
            desc = tool.description or ""
            assert "[DEPRECATED]" in desc, (
                f"Tool '{name}' should be marked [DEPRECATED], got: {desc[:100]}"
            )


# ============================================================
# Guide Tool
# ============================================================

class TestGuideToolWorkflows:
    """Test the agentbase_get_workflow_guide tool returns valid recipes."""

    @pytest.mark.asyncio
    async def test_guide_no_goal_returns_catalog(self):
        """Calling with empty goal returns all available workflows."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("")
        assert "available_workflows" in result
        workflows = result["available_workflows"]
        assert len(workflows) >= 10
        # Each workflow has key, title, description
        for wf in workflows:
            assert "key" in wf
            assert "title" in wf
            assert "description" in wf

    @pytest.mark.asyncio
    async def test_guide_exact_key_match(self):
        """Passing an exact workflow key returns that workflow."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("build_web_library")
        assert "workflow" in result
        assert result["matched_by"] == "exact_key"
        wf = result["workflow"]
        assert "steps" in wf
        assert len(wf["steps"]) > 0
        # Each step has required fields
        for step in wf["steps"]:
            assert "step" in step
            assert "action" in step
            assert "tool" in step

    @pytest.mark.asyncio
    async def test_guide_keyword_match(self):
        """Natural language goals match via keywords."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("I want to build a knowledge library from a website")
        assert "workflow" in result
        assert result["matched_by"] == "keyword"
        assert result["workflow"]["title"] == "Build a knowledge library from web sources"

    @pytest.mark.asyncio
    async def test_guide_search_keyword_match(self):
        """Search-related goals match the search workflow."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("how to search indexed content")
        assert "workflow" in result
        assert "search" in result["workflow"]["title"].lower()

    @pytest.mark.asyncio
    async def test_guide_taxonomy_keyword_match(self):
        """Taxonomy goals match the taxonomy workflow."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("set up taxonomy classification")
        assert "workflow" in result
        assert "taxonomy" in result["workflow"]["title"].lower()

    @pytest.mark.asyncio
    async def test_guide_evaluation_workflow(self):
        """The evaluation/experiment recipe exists and matches eval goals."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("evaluate_and_experiment")
        assert result["matched_by"] == "exact_key"
        steps = result["workflow"]["steps"]
        assert [s["tool"] for s in steps] == [
            "agentbase_create_question_set", "agentbase_add_question",
            "agentbase_run_scorecard", "agentbase_create_experiment",
            "agentbase_compare_experiment", "agentbase_get_comparison",
            "agentbase_promote_experiment",
        ]

        by_goal = await agentbase_get_workflow_guide("run a scorecard and a/b test my agent")
        assert by_goal["workflow"]["title"].startswith("Evaluate")

    @pytest.mark.asyncio
    async def test_guide_no_match_returns_suggestions(self):
        """Unmatched goals return available workflows as suggestions."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("make me a sandwich")
        assert "error" in result
        assert "available_workflows" in result

    @pytest.mark.asyncio
    async def test_guide_agent_keyword_match(self):
        """Agent-related goals match the configure_agent workflow."""
        from app.mcp.tools.guide import agentbase_get_workflow_guide

        result = await agentbase_get_workflow_guide("configure an agent with knowledge access")
        assert "workflow" in result
        assert "agent" in result["workflow"]["title"].lower()

    @pytest.mark.asyncio
    async def test_guide_steps_reference_real_tools(self):
        """All tool names in guide steps should exist in the MCP server."""
        from app.mcp.server import mcp
        from app.mcp.tools.guide import WORKFLOWS

        registered = set(mcp._tool_manager._tools.keys())

        for key, wf in WORKFLOWS.items():
            for step in wf["steps"]:
                tool_name = step["tool"]
                assert tool_name in registered, (
                    f"Workflow '{key}' step {step['step']} references "
                    f"non-existent tool '{tool_name}'"
                )


# ============================================================
# Tool Description Quality
# ============================================================

class TestDescriptionQuality:
    """Verify description conventions across all tools."""

    def test_no_empty_descriptions(self):
        """Every tool must have a non-empty description."""
        from app.mcp.server import mcp

        tools = mcp._tool_manager._tools
        for name, tool in tools.items():
            desc = tool.description or ""
            assert len(desc.strip()) > 0, f"Tool '{name}' has empty description"

    def test_descriptions_are_concise(self):
        """No description should exceed 300 characters (context window goal)."""
        from app.mcp.server import mcp

        tools = mcp._tool_manager._tools
        for name, tool in tools.items():
            desc = tool.description or ""
            assert len(desc) <= 300, (
                f"Tool '{name}' description is {len(desc)} chars (max 300): {desc[:100]}..."
            )


# ============================================================
# Individual Tool Response Shapes (with mocked services)
# ============================================================

class TestProjectTools:
    """Test deprecated project tools still work."""

    @pytest.mark.asyncio
    async def test_list_projects_returns_list(self):
        """agentbase_list_projects should return a list."""
        from app.mcp.tools.projects import agentbase_list_projects

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.mcp.tools.projects.async_session_maker") as mock_maker:
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_list_projects()
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_project_not_found(self):
        """agentbase_get_project returns error dict when project not found."""
        from app.mcp.tools.projects import agentbase_get_project

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.mcp.tools.projects.async_session_maker") as mock_maker:
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_project("nonexistent-id")
            assert "error" in result
            assert "not found" in result["error"].lower()


class TestAgentTools:
    """Test agent tool response shapes."""

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self):
        """agentbase_get_agent returns error for non-existent agent."""
        from app.mcp.tools.agents import agentbase_get_agent

        mock_service = AsyncMock()
        mock_service.get_agent.return_value = None

        with patch("app.mcp.tools.agents.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.agents.AgentService", return_value=mock_service):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_agent("bad-id")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self):
        """agentbase_delete_agent returns error for non-existent agent."""
        from app.mcp.tools.agents import agentbase_delete_agent

        mock_service = AsyncMock()
        mock_service.delete_agent.return_value = False

        with patch("app.mcp.tools.agents.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.agents.AgentService", return_value=mock_service), \
             patch("app.mcp.tools.agents.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_delete_agent("bad-id")
            assert "error" in result


class TestLibraryTools:
    """Test library tool response shapes."""

    @pytest.mark.asyncio
    async def test_get_library_not_found(self):
        """agentbase_get_library returns error for non-existent library."""
        from app.mcp.tools.libraries import agentbase_get_library

        mock_svc_instance = AsyncMock()
        mock_svc_instance.get_kb.return_value = None

        mock_lib_cls = MagicMock(return_value=mock_svc_instance)
        with patch("app.mcp.tools.libraries.async_session_maker") as mock_maker, \
             patch("app.services.library.service.LibraryService", mock_lib_cls):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_library("bad-id")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_library_parameter_is_library_id(self):
        """Verify library tools use library_id not kb_id."""
        import inspect
        from app.mcp.tools.libraries import (
            agentbase_get_library, agentbase_update_library, agentbase_delete_library,
            agentbase_add_source_to_library, agentbase_remove_source_from_library,
            agentbase_recalculate_library_stats,
        )

        for fn in [agentbase_get_library, agentbase_update_library, agentbase_delete_library,
                    agentbase_add_source_to_library, agentbase_remove_source_from_library,
                    agentbase_recalculate_library_stats]:
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            assert "kb_id" not in params, (
                f"{fn.__name__} still uses 'kb_id' — should be 'library_id'"
            )
            if fn.__name__ != "agentbase_list_libraries":
                assert "library_id" in params, (
                    f"{fn.__name__} is missing 'library_id' parameter"
                )


class TestEvaluationTools:
    """Test evaluation question-set tool response shapes."""

    @pytest.mark.asyncio
    async def test_get_question_set_not_found(self):
        """agentbase_get_question_set returns error for non-existent set."""
        from app.mcp.tools.evaluation import agentbase_get_question_set

        mock_service = AsyncMock()
        mock_service.get_set.return_value = None

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.QuestionSetService", MagicMock(return_value=mock_service)):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_question_set("bad-id")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_question_not_found(self):
        """agentbase_delete_question returns error for non-existent question."""
        from app.mcp.tools.evaluation import agentbase_delete_question

        mock_service = AsyncMock()
        mock_service.delete_question.return_value = None

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.QuestionSetService", MagicMock(return_value=mock_service)), \
             patch("app.mcp.tools.evaluation.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_delete_question("bad-id")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_question_archives_with_results(self):
        """agentbase_delete_question surfaces the service's 'archived' outcome."""
        from app.mcp.tools.evaluation import agentbase_delete_question

        mock_service = AsyncMock()
        mock_service.delete_question.return_value = "archived"

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.QuestionSetService", MagicMock(return_value=mock_service)), \
             patch("app.mcp.tools.evaluation.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_delete_question("q-1")
            assert result == {"outcome": "archived"}

    @pytest.mark.asyncio
    async def test_get_experiment_not_found(self):
        """agentbase_get_experiment returns error for non-existent experiment."""
        from app.mcp.tools.evaluation import agentbase_get_experiment

        mock_service = AsyncMock()
        mock_service.get_experiment.return_value = None

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.ExperimentService", MagicMock(return_value=mock_service)):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_experiment("bad-id")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_create_experiment_service_error_surfaced(self):
        """agentbase_create_experiment surfaces service ValueError as error string."""
        from app.mcp.tools.evaluation import agentbase_create_experiment

        mock_service = AsyncMock()
        mock_service.create_experiment.side_effect = ValueError(
            "Non-overridable keys: chunk_size")

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.ExperimentService", MagicMock(return_value=mock_service)), \
             patch("app.mcp.tools.evaluation.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_create_experiment(
                library_id="l1", agent_id="a1", name="x",
                overrides={"chunk_size": 512})
            assert "chunk_size" in result["error"]

    @pytest.mark.asyncio
    async def test_compare_experiment_returns_run_ids_and_next(self):
        """agentbase_compare_experiment returns both run ids with a polling hint."""
        from app.mcp.tools.evaluation import agentbase_compare_experiment

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.start_comparison",
                   new=AsyncMock(return_value={"baseline_run_id": "b1",
                                               "experiment_run_id": "e1"})), \
             patch("app.mcp.tools.evaluation.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_compare_experiment("x1", "qs1")
            assert result["baseline_run_id"] == "b1"
            assert result["experiment_run_id"] == "e1"
            assert "agentbase_get_comparison" in result["next"]

    @pytest.mark.asyncio
    async def test_get_comparison_unfinished_run_error(self):
        """agentbase_get_comparison surfaces unfinished-run ValueError as error string."""
        from app.mcp.tools.evaluation import agentbase_get_comparison

        with patch("app.mcp.tools.evaluation.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.evaluation.load_comparison",
                   new=AsyncMock(side_effect=ValueError("Run has not finished"))):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_comparison("b1", "e1")
            assert "error" in result


class TestSourceTools:
    """Test source tool response shapes."""

    @pytest.mark.asyncio
    async def test_get_source_not_found(self):
        """agentbase_get_source returns error for non-existent source."""
        from app.mcp.tools.sources import agentbase_get_source

        mock_service = AsyncMock()
        mock_service.get_source.return_value = None

        with patch("app.mcp.tools.sources.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.sources.IngestionService", return_value=mock_service):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_get_source("bad-id")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_list_filter_fields_returns_fields(self):
        """agentbase_list_filter_fields returns a static list of field definitions."""
        from app.mcp.tools.sources import agentbase_list_filter_fields

        result = await agentbase_list_filter_fields()
        assert "fields" in result
        fields = result["fields"]
        assert len(fields) > 0
        # Each field has name and description
        for f in fields:
            assert "name" in f
            assert "description" in f
        # Key fields present
        field_names = [f["name"] for f in fields]
        assert "platforms" in field_names
        assert "doc_category" in field_names

    @pytest.mark.asyncio
    async def test_search_mutual_exclusion(self):
        """agentbase_search_sources rejects both source_ids and knowledge_base_id."""
        from app.mcp.tools.sources import agentbase_search_sources

        with patch("app.mcp.tools.sources.async_session_maker"):
            result = await agentbase_search_sources(
                query="test",
                source_ids=["a"],
                knowledge_base_id="b",
            )
            assert isinstance(result, list)
            assert "error" in result[0]
            assert "mutually exclusive" in result[0]["error"].lower()


class TestGuideRecipeIntegrity:
    """Ensure guide recipes are internally consistent."""

    def test_all_recipes_have_required_fields(self):
        """Every recipe has title, description, and steps."""
        from app.mcp.tools.guide import WORKFLOWS

        for key, wf in WORKFLOWS.items():
            assert "title" in wf, f"Recipe '{key}' missing title"
            assert "description" in wf, f"Recipe '{key}' missing description"
            assert "steps" in wf, f"Recipe '{key}' missing steps"
            assert len(wf["steps"]) >= 2, (
                f"Recipe '{key}' has only {len(wf['steps'])} steps"
            )

    def test_steps_are_numbered_sequentially(self):
        """Steps should be numbered 1, 2, 3, ..."""
        from app.mcp.tools.guide import WORKFLOWS

        for key, wf in WORKFLOWS.items():
            step_nums = [s["step"] for s in wf["steps"]]
            expected = list(range(1, len(step_nums) + 1))
            assert step_nums == expected, (
                f"Recipe '{key}' steps out of order: {step_nums}"
            )

    def test_keyword_map_covers_all_recipes(self):
        """Every recipe in WORKFLOWS should have keywords."""
        from app.mcp.tools.guide import WORKFLOWS, _KEYWORD_MAP

        for key in WORKFLOWS:
            assert key in _KEYWORD_MAP, (
                f"Recipe '{key}' has no keyword entry in _KEYWORD_MAP"
            )


# ============================================================
# Tool Annotations
# ============================================================

class TestAnnotations:
    """Verify all tools have proper annotations set."""

    def test_all_tools_have_annotations(self):
        """Every tool must have annotations."""
        from app.mcp.server import mcp
        tools = mcp._tool_manager._tools
        for name, tool in tools.items():
            assert tool.annotations is not None, f"Tool '{name}' missing annotations"

    def test_read_only_tools_annotated_correctly(self):
        """Read-only tools must have readOnlyHint=True, destructiveHint=False."""
        from app.mcp.server import mcp
        tools = mcp._tool_manager._tools
        read_only = [
            "agentbase_list_sources", "agentbase_get_source", "agentbase_get_source_status",
            "agentbase_search_sources", "agentbase_deep_search", "agentbase_list_filter_values",
            "agentbase_list_filter_fields", "agentbase_get_full_document", "agentbase_export_source_chunks",
            "agentbase_get_indexing_queue", "agentbase_get_source_analytics",
            "agentbase_get_watcher_statuses", "agentbase_get_watcher_status",
            "agentbase_list_stale_sources", "agentbase_get_library_coverage",
            "agentbase_list_libraries", "agentbase_get_library",
            "agentbase_list_agents", "agentbase_get_agent", "agentbase_list_agent_knowledge_bases",
            "agentbase_list_taxonomies", "agentbase_get_taxonomy", "agentbase_list_taxonomy_terms",
            "agentbase_list_taxonomy_suggestions", "agentbase_get_taxonomy_coverage",
            "agentbase_list_projects", "agentbase_get_project",
            "agentbase_get_workflow_guide",
            "agentbase_discover_library", "agentbase_search_library",
        ]
        for name in read_only:
            tool = tools.get(name)
            if tool is None:
                continue
            a = tool.annotations
            assert a.readOnlyHint is True, f"Tool '{name}' should be readOnlyHint=True"
            assert a.destructiveHint is False, f"Tool '{name}' should be destructiveHint=False"

    def test_destructive_tools_annotated_correctly(self):
        """Destructive tools must have destructiveHint=True."""
        from app.mcp.server import mcp
        tools = mcp._tool_manager._tools
        destructive = [
            "agentbase_delete_source", "agentbase_delete_document", "agentbase_delete_library",
            "agentbase_delete_agent", "agentbase_delete_taxonomy", "agentbase_delete_taxonomy_term",
        ]
        for name in destructive:
            tool = tools.get(name)
            if tool is None:
                continue
            a = tool.annotations
            assert a.destructiveHint is True, f"Tool '{name}' should be destructiveHint=True"
            assert a.readOnlyHint is False, f"Tool '{name}' should be readOnlyHint=False"


# ============================================================
# Server Naming Convention
# ============================================================

class TestServerNaming:
    """Verify server follows naming convention."""

    def test_server_name_convention(self):
        """Server name should follow {service}_mcp convention."""
        from app.mcp.server import mcp
        assert mcp.name == "agentbase_mcp", f"Server name should be 'agentbase_mcp', got '{mcp.name}'"


# ============================================================
# Source Module Split
# ============================================================

class TestModuleSplit:
    """Verify source file split imports correctly."""

    def test_sources_upload_tools_registered(self):
        """Upload tools from sources_upload.py should be registered."""
        from app.mcp.server import mcp
        tools = mcp._tool_manager._tools
        upload_tools = ["agentbase_upload_source_file", "agentbase_upload_source_files", "agentbase_add_files_to_source"]
        for name in upload_tools:
            assert name in tools, f"Upload tool '{name}' not registered after split"

    def test_sources_docs_tools_registered(self):
        """Document tools from sources_docs.py should be registered."""
        from app.mcp.server import mcp
        tools = mcp._tool_manager._tools
        doc_tools = ["agentbase_get_full_document", "agentbase_delete_document", "agentbase_export_source_chunks", "agentbase_get_indexing_queue"]
        for name in doc_tools:
            assert name in tools, f"Document tool '{name}' not registered after split"


# ============================================================
# Input Validation Schemas (#85 item 2)
# ============================================================

class TestInputValidationSchemas:
    """High-traffic tools declare Field() constraints in flat schemas.

    The Annotated[..., Field(...)] pattern was chosen over BaseModel params
    because the installed MCP SDK nests a BaseModel param under a single
    'params' object in the client-facing schema, while Annotated fields stay
    flat and still carry constraints into the JSON schema.
    """

    def _schema(self, name: str) -> dict:
        from app.mcp.server import mcp
        return mcp._tool_manager._tools[name].parameters

    def test_schemas_are_flat_not_nested(self):
        """No tool wraps its arguments in a nested 'params' object."""
        expected_flat_field = {
            "agentbase_search_sources": "query",
            "agentbase_deep_search": "query",
            "agentbase_create_source": "source_type",
            "agentbase_create_library": "name",
            "agentbase_create_agent": "system_prompt",
        }
        for tool_name, field in expected_flat_field.items():
            props = self._schema(tool_name)["properties"]
            assert "params" not in props, f"{tool_name} schema is nested"
            assert field in props, f"{tool_name} schema missing flat field '{field}'"

    def test_no_new_required_params(self):
        """Added validation must not change which params are required."""
        expected_required = {
            "agentbase_search_sources": {"query"},
            "agentbase_deep_search": {"query"},
            "agentbase_create_source": {"name", "source_type", "source_path"},
            "agentbase_create_library": {"name"},
            "agentbase_create_agent": {"name", "system_prompt", "model_provider", "model_name"},
        }
        for tool_name, required in expected_required.items():
            schema = self._schema(tool_name)
            assert set(schema.get("required", [])) == required, (
                f"{tool_name} required params changed: {schema.get('required')}"
            )

    def test_search_sources_constraints(self):
        props = self._schema("agentbase_search_sources")["properties"]
        assert props["query"]["minLength"] == 1
        assert props["query"]["maxLength"] == 2000
        assert props["top_k"]["minimum"] == 1
        assert props["top_k"]["maximum"] == 50
        assert props["vector_weight"]["minimum"] == 0.0
        assert props["vector_weight"]["maximum"] == 1.0
        assert props["include_neighbors"]["minimum"] == 0
        assert props["include_neighbors"]["maximum"] == 10

    def test_deep_search_constraints(self):
        props = self._schema("agentbase_deep_search")["properties"]
        assert props["query"]["minLength"] == 1
        assert props["top_k"]["minimum"] == 1
        assert props["top_k"]["maximum"] == 50
        assert props["max_sub_queries"]["minimum"] == 1
        assert props["max_sub_queries"]["maximum"] == 10

    def test_create_source_constraints(self):
        props = self._schema("agentbase_create_source")["properties"]
        assert props["name"]["minLength"] == 1
        assert props["name"]["maxLength"] == 255
        assert props["source_type"]["enum"] == ["url", "file", "directory", "youtube"]
        assert props["source_path"]["maxLength"] == 2048
        # Optional Literal renders as anyOf [enum, null]
        freshness_variants = props["freshness_policy"]["anyOf"]
        enums = [v for v in freshness_variants if "enum" in v]
        assert enums and enums[0]["enum"] == ["none", "automatic", "manual"]

    def test_create_library_constraints(self):
        props = self._schema("agentbase_create_library")["properties"]
        assert props["name"]["minLength"] == 1
        assert props["name"]["maxLength"] == 255
        dim_variants = props["embedding_dimensions"]["anyOf"]
        constrained = [v for v in dim_variants if "minimum" in v]
        assert constrained and constrained[0]["minimum"] == 1
        assert constrained[0]["maximum"] == 16384

    def test_create_agent_constraints(self):
        props = self._schema("agentbase_create_agent")["properties"]
        assert props["name"]["minLength"] == 1
        assert props["system_prompt"]["minLength"] == 1
        assert props["temperature"]["minimum"] == 0.0
        assert props["temperature"]["maximum"] == 2.0
        assert props["rag_top_k"]["minimum"] == 1
        assert props["rag_top_k"]["maximum"] == 50

    def test_generate_questions_constraints(self):
        props = self._schema("agentbase_generate_questions")["properties"]
        assert props["questions_per_doc"]["minimum"] == 1
        assert props["questions_per_doc"]["maximum"] == 10
        assert props["doc_sample_size"]["minimum"] == 1
        assert props["doc_sample_size"]["maximum"] == 100
        # Optional int renders as anyOf [constrained int, null]
        count_variants = props["count"]["anyOf"]
        constrained = [v for v in count_variants if "minimum" in v]
        assert constrained and constrained[0]["minimum"] == 5
        assert constrained[0]["maximum"] == 50


# ============================================================
# Input Validation Errors surface as MCP errors (#85 item 2)
# ============================================================

class TestInputValidationErrors:
    """Out-of-range args are rejected by validation as proper MCP errors.

    The lowlevel MCP server validates arguments against the tool's
    inputSchema before invoking the tool, and converts any tool-layer
    exception (including Pydantic ToolError) into a CallToolResult with
    isError=True — never an unhandled 500.
    """

    async def _call_via_lowlevel(self, name: str, arguments: dict):
        from mcp import types
        from app.mcp.server import mcp

        handler = mcp._mcp_server.request_handlers[types.CallToolRequest]
        req = types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name=name, arguments=arguments),
        )
        return await handler(req)

    @pytest.mark.asyncio
    async def test_deep_search_top_k_too_large_is_mcp_error(self):
        """top_k=999 is rejected before the tool body runs (no clamping)."""
        from mcp import types

        result = await self._call_via_lowlevel(
            "agentbase_deep_search", {"query": "acme quarterly plan", "top_k": 999}
        )
        assert isinstance(result.root, types.CallToolResult)
        assert result.root.isError is True
        text = result.root.content[0].text
        assert "50" in text  # maximum surfaced in the validation message

    @pytest.mark.asyncio
    async def test_search_sources_top_k_zero_is_mcp_error(self):
        from mcp import types

        result = await self._call_via_lowlevel(
            "agentbase_search_sources", {"query": "acme", "top_k": 0}
        )
        assert isinstance(result.root, types.CallToolResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_create_library_empty_name_is_mcp_error(self):
        from mcp import types

        result = await self._call_via_lowlevel("agentbase_create_library", {"name": ""})
        assert isinstance(result.root, types.CallToolResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_create_source_bad_source_type_is_mcp_error(self):
        from mcp import types

        result = await self._call_via_lowlevel(
            "agentbase_create_source",
            {"name": "ACME Docs", "source_type": "ftp", "source_path": "ftp://acme.example"},
        )
        assert isinstance(result.root, types.CallToolResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_create_agent_temperature_out_of_range_is_mcp_error(self):
        from mcp import types

        result = await self._call_via_lowlevel(
            "agentbase_create_agent",
            {
                "name": "ACME Agent",
                "system_prompt": "You are a helpful assistant.",
                "model_provider": "ollama",
                "model_name": "test-model",
                "temperature": 5.0,
            },
        )
        assert isinstance(result.root, types.CallToolResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_pydantic_layer_raises_tool_error_not_500(self):
        """FastMCP's Pydantic validation raises ToolError (converted to an
        MCP error result by the server), not an unhandled exception type."""
        from mcp.server.fastmcp.exceptions import ToolError
        from app.mcp.server import mcp

        with pytest.raises(ToolError) as exc_info:
            await mcp._tool_manager.call_tool(
                "agentbase_deep_search", {"query": "acme", "top_k": 999}
            )
        assert "top_k" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_valid_boundary_call_passes_validation(self):
        """top_k=50 (the boundary) passes validation and reaches the tool body."""
        from app.mcp.server import mcp

        mock_result = MagicMock()
        mock_result.results = []
        mock_result.stats = {"sub_query_count": 1, "total_candidates": 0,
                             "total_time_ms": 5}
        mock_rag = AsyncMock()
        mock_rag.deep_search.return_value = mock_result

        with patch("app.mcp.tools.sources.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.sources.RAGService", return_value=mock_rag):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await mcp._tool_manager.call_tool(
                "agentbase_deep_search", {"query": "acme quarterly plan", "top_k": 50}
            )
        assert result["results"] == []
        assert result["stats"]["sub_query_count"] == 1

    @pytest.mark.asyncio
    async def test_deep_search_no_longer_clamps(self):
        """Direct call with in-range args passes exact values through."""
        from app.mcp.tools.sources import agentbase_deep_search

        mock_result = MagicMock()
        mock_result.results = []
        mock_result.stats = {}
        mock_rag = AsyncMock()
        mock_rag.deep_search.return_value = mock_result

        with patch("app.mcp.tools.sources.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.sources.RAGService", return_value=mock_rag):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            await agentbase_deep_search(query="acme", top_k=37, max_sub_queries=9)

        call_kwargs = mock_rag.deep_search.call_args.kwargs
        assert call_kwargs["top_k"] == 37
        assert call_kwargs["max_sub_queries"] == 9


# ============================================================
# Long-running tool return contracts (#85 item 3)
# ============================================================

class TestLongRunningToolPayloads:
    """Fire-and-return tools describe how to track their background work.

    ctx.report_progress is not viable here: the server runs with
    stateless_http=True and json_response=True, where the streamable HTTP
    transport discards notifications, and the background work happens after
    the request context is gone. The return payloads carry job_id (when the
    job queue provides one), a next_step polling hint, and duration guidance
    instead.
    """

    @pytest.mark.asyncio
    async def test_index_source_payload_self_describing(self):
        import asyncio as _asyncio
        from app.mcp.tools.sources import agentbase_index_source

        mock_source = MagicMock()
        mock_source.name = "ACME Docs"
        mock_service = AsyncMock()
        mock_service.get_source.return_value = mock_source
        mock_service.start_indexing.return_value = "started"

        with patch("app.mcp.tools.sources.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.sources.IngestionService", return_value=mock_service), \
             patch("app.mcp.tools.sources.check_mcp_scope"), \
             patch("app.mcp.tools.sources.run_indexing_task", new=AsyncMock()), \
             patch("app.mcp.tools.sources.publish_source_event", new=AsyncMock()):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_index_source("src-1")
            await _asyncio.sleep(0)  # let the created background task settle

        assert result["status"] == "indexing"
        assert result["source_id"] == "src-1"
        assert "agentbase_get_source_status" in result["next_step"]
        assert "expected_duration" in result

    @pytest.mark.asyncio
    async def test_index_source_already_indexing_has_next_step(self):
        from app.mcp.tools.sources import agentbase_index_source

        mock_source = MagicMock()
        mock_source.name = "ACME Docs"
        mock_service = AsyncMock()
        mock_service.get_source.return_value = mock_source
        mock_service.start_indexing.return_value = "already_indexing"

        with patch("app.mcp.tools.sources.async_session_maker") as mock_maker, \
             patch("app.mcp.tools.sources.IngestionService", return_value=mock_service), \
             patch("app.mcp.tools.sources.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_index_source("src-1")

        assert result["status"] == "indexing"
        assert "agentbase_get_source_status" in result["next_step"]

    @pytest.mark.asyncio
    async def test_refresh_source_payload_has_job_id_and_next_step(self):
        from app.mcp.tools.source_ops import agentbase_refresh_source

        mock_source = MagicMock()
        mock_source.source_type = "url"
        mock_source.status = "indexed"
        mock_source.project_id = None
        mock_service = AsyncMock()
        mock_service.get_source.return_value = mock_source

        mock_job_service = AsyncMock()
        mock_job_service.enqueue.return_value = MagicMock(id="job-refresh-1")

        with patch("app.mcp.tools.source_ops.async_session_maker") as mock_maker, \
             patch("app.services.IngestionService", return_value=mock_service), \
             patch("app.services.job_service.JobService", MagicMock(return_value=mock_job_service)), \
             patch("app.mcp.tools.source_ops.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_refresh_source("src-1")

        assert result["status"] == "indexing"
        assert result["job_id"] == "job-refresh-1"
        assert result["mode"] == "full"
        assert "agentbase_get_source_status" in result["next_step"]
        assert "expected_duration" in result

    @pytest.mark.asyncio
    async def test_re_enrich_source_payload_has_job_id_and_next_step(self):
        from app.mcp.tools.source_ops import agentbase_re_enrich_source

        mock_source = MagicMock()
        mock_source.collection_name = "src_acme_docs"
        mock_source.enrichment_taxonomy_id = "tax-1"
        mock_source.status = "indexed"
        mock_source.project_id = None
        mock_service = AsyncMock()
        mock_service.get_source.return_value = mock_source

        mock_job_service = AsyncMock()
        mock_job_service.enqueue.return_value = MagicMock(id="job-enrich-1")

        with patch("app.mcp.tools.source_ops.async_session_maker") as mock_maker, \
             patch("app.services.IngestionService", return_value=mock_service), \
             patch("app.services.job_service.JobService", MagicMock(return_value=mock_job_service)), \
             patch("app.mcp.tools.source_ops.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_re_enrich_source("src-1")

        assert result["status"] == "queued"
        assert result["job_id"] == "job-enrich-1"
        assert "agentbase_get_source_status" in result["next_step"]
        assert "expected_duration" in result

    @pytest.mark.asyncio
    async def test_scan_url_synchronous_contract_unchanged(self):
        """agentbase_scan_url stays synchronous; its return contract is the site tree."""
        from app.mcp.tools.source_ops import agentbase_scan_url

        node = MagicMock()
        node.url = "https://acme.example"
        node.title = "ACME"
        node.path = "/"
        node.children = []
        mock_result = MagicMock()
        mock_result.tree = node
        mock_result.sitemap_url = None

        mock_service = AsyncMock()
        mock_service.scan_url.return_value = mock_result

        with patch("app.mcp.tools.source_ops.async_session_maker") as mock_maker, \
             patch("app.services.IngestionService", return_value=mock_service), \
             patch("app.mcp.tools.source_ops.check_mcp_scope"):
            mock_session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agentbase_scan_url("https://acme.example")

        assert result["total_urls"] == 1
        assert result["urls"] == ["https://acme.example"]
        assert result["tree"]["url"] == "https://acme.example"
