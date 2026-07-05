"""
MCP Workflow Guide Tool

Returns structured workflow recipes for common goals. Helps agents discover
tool sequences without needing to hold all 84 tool descriptions in context.
"""

from app.mcp.server import mcp

# ============================================================
# Workflow Recipes
# ============================================================

WORKFLOWS: dict[str, dict] = {
    "build_web_library": {
        "title": "Build a knowledge library from web sources",
        "description": (
            "Create a searchable knowledge library from a website or documentation URL. "
            "The full pipeline: create source, index it, create a library, link them."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Create a source from the URL",
                "tool": "agentbase_create_source",
                "params": {
                    "name": "My Docs",
                    "source_type": "url",
                    "source_path": "https://docs.example.com",
                },
                "notes": "Use selected_urls to limit to specific pages. Set embedding_provider/model if you have a preference.",
            },
            {
                "step": 2,
                "action": "Start indexing (scrape, chunk, embed)",
                "tool": "agentbase_index_source",
                "params": {"source_id": "<from step 1>"},
                "notes": "Runs in background. Returns immediately.",
            },
            {
                "step": 3,
                "action": "Poll until indexing completes",
                "tool": "agentbase_get_source_status",
                "params": {"source_id": "<from step 1>"},
                "notes": "Wait until status is 'indexed'. Check progress/progress_total for completion %.",
            },
            {
                "step": 4,
                "action": "Create a library (Qdrant collection container)",
                "tool": "agentbase_create_library",
                "params": {
                    "name": "My Library",
                    "embedding_provider": "<must match source>",
                    "embedding_model": "<must match source>",
                },
                "notes": "Embedding provider/model MUST match the source's embedding settings.",
            },
            {
                "step": 5,
                "action": "Add the indexed source to the library",
                "tool": "agentbase_add_source_to_library",
                "params": {
                    "library_id": "<from step 4>",
                    "source_id": "<from step 1>",
                },
                "notes": "A library can hold multiple sources. Repeat for each source you want included.",
            },
            {
                "step": 6,
                "action": "Test with a search query",
                "tool": "agentbase_search_sources",
                "params": {
                    "query": "your test question",
                    "knowledge_base_id": "<library_id from step 4>",
                },
                "notes": "Use hybrid=True (default) for best results. Add filters for precision.",
            },
        ],
    },
    "build_file_library": {
        "title": "Build a knowledge library from local files",
        "description": (
            "Index local files (PDF, DOCX, etc.) or a directory into a searchable library."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Create a source from the file or directory path",
                "tool": "agentbase_create_source",
                "params": {
                    "name": "My Files",
                    "source_type": "directory",
                    "source_path": "/path/to/documents",
                },
                "notes": "Use source_type='file' for a single file, 'directory' for a folder. Or use agentbase_upload_source_file for base64 upload.",
            },
            {
                "step": 2,
                "action": "Start indexing",
                "tool": "agentbase_index_source",
                "params": {"source_id": "<from step 1>"},
            },
            {
                "step": 3,
                "action": "Poll until indexing completes",
                "tool": "agentbase_get_source_status",
                "params": {"source_id": "<from step 1>"},
            },
            {
                "step": 4,
                "action": "Create a library and add the source",
                "tool": "agentbase_create_library",
                "params": {
                    "name": "My File Library",
                    "embedding_provider": "<must match source>",
                    "embedding_model": "<must match source>",
                },
            },
            {
                "step": 5,
                "action": "Link source to library",
                "tool": "agentbase_add_source_to_library",
                "params": {
                    "library_id": "<from step 4>",
                    "source_id": "<from step 1>",
                },
            },
        ],
    },
    "create_sub_source": {
        "title": "Create a sub-source over an existing directory root",
        "description": (
            "Sub-sources are filtered views over a root directory source. They share the "
            "parent root's watcher and chunks, but only return results from a specific "
            "subfolder. Use to give agents narrow access to a slice of a large tree "
            "(e.g. 'ACME/Q4-Plan') without re-indexing or duplicating data."
        ),
        "steps": [
            {
                "step": 1,
                "action": "List existing directory roots",
                "tool": "agentbase_list_sources",
                "params": {"parent_source_id": "root"},
                "notes": "Pass 'root' to filter to top-level directory sources only.",
            },
            {
                "step": 2,
                "action": "Create the sub-source",
                "tool": "agentbase_create_source",
                "params": {
                    "name": "ACME Q4 Plan",
                    "source_type": "directory",
                    "source_path": "ignored",
                    "parent_source_id": "<root id from step 1>",
                    "path_prefix": "/data/documents/ACME/Q4-Plan",
                },
                "notes": (
                    "path_prefix must be under the parent root's source_path. Optionally "
                    "pass path_excludes to further narrow. Sub-sources don't own a "
                    "Qdrant collection — queries hit the parent's collection with a "
                    "folder_ancestors filter."
                ),
            },
            {
                "step": 3,
                "action": "Bind the sub-source to a library",
                "tool": "agentbase_add_source_to_library",
                "params": {
                    "library_id": "<existing library>",
                    "source_id": "<from step 2>",
                },
                "notes": "An agent bound to the library will then search only the sub-source's subtree.",
            },
        ],
    },
    "setup_taxonomy": {
        "title": "Set up taxonomy-based classification for sources",
        "description": (
            "Create a taxonomy with facets and terms, then enable enrichment on sources "
            "so indexed content is automatically classified."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Create a taxonomy",
                "tool": "agentbase_create_taxonomy",
                "params": {"name": "My Classification Scheme"},
            },
            {
                "step": 2,
                "action": "Add terms to each facet",
                "tool": "agentbase_add_taxonomy_term",
                "params": {
                    "taxonomy_id": "<from step 1>",
                    "facet": "platform",
                    "value": "AcmeCRM",
                    "keywords": ["acmecrm", "acme crm"],
                },
                "notes": "Repeat for each term in each facet. Common facets: platform, product, doc_category, topic.",
            },
            {
                "step": 3,
                "action": "Link taxonomy to a library",
                "tool": "agentbase_update_library",
                "params": {
                    "library_id": "<your library>",
                    "taxonomy_id": "<from step 1>",
                    "enrichment_model": "gemma3:12b",
                },
                "notes": "enrichment_model is the LLM used for classification. Must be available via a configured provider.",
            },
            {
                "step": 4,
                "action": "Re-enrich existing sources to apply classification",
                "tool": "agentbase_re_enrich_source",
                "params": {"source_id": "<source to classify>"},
                "notes": "Only needed for already-indexed sources. New indexing jobs auto-classify if taxonomy is linked.",
            },
            {
                "step": 5,
                "action": "Review classification coverage",
                "tool": "agentbase_get_taxonomy_coverage",
                "params": {"taxonomy_id": "<from step 1>"},
            },
            {
                "step": 6,
                "action": "Review and approve auto-suggested terms",
                "tool": "agentbase_list_taxonomy_suggestions",
                "params": {"taxonomy_id": "<from step 1>", "status": "pending"},
                "notes": "During enrichment, the LLM may suggest new terms. Use agentbase_approve_taxonomy_suggestion or agentbase_reject_taxonomy_suggestion.",
            },
        ],
    },
    "search_content": {
        "title": "Search across indexed content",
        "description": (
            "Search your indexed knowledge using semantic, hybrid, or deep search. "
            "Includes filtering by metadata fields."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Simple search (most common)",
                "tool": "agentbase_search_sources",
                "params": {
                    "query": "your question here",
                    "top_k": 5,
                },
                "notes": "Defaults to hybrid search with reranking. Add source_ids or knowledge_base_id to scope.",
            },
            {
                "step": 2,
                "action": "Discover available filter fields",
                "tool": "agentbase_list_filter_fields",
                "notes": "Returns available metadata filter fields (platforms, products, doc_category, etc.).",
            },
            {
                "step": 3,
                "action": "Discover filter values for a field",
                "tool": "agentbase_list_filter_values",
                "params": {"field": "platforms"},
                "notes": "Shows actual values present in the indexed data.",
            },
            {
                "step": 4,
                "action": "Filtered search",
                "tool": "agentbase_search_sources",
                "params": {
                    "query": "your question",
                    "filters": {"platforms": ["AcmeCRM"]},
                },
                "notes": "Filters AND across keys, OR within a key's list.",
            },
            {
                "step": 5,
                "action": "Deep search for complex questions",
                "tool": "agentbase_deep_search",
                "params": {"query": "complex multi-part question"},
                "notes": "Use when question spans multiple entities or aspects. Adds 1-3s latency vs agentbase_search_sources.",
            },
        ],
    },
    "configure_agent": {
        "title": "Configure an agent with knowledge access",
        "description": (
            "Create an AI agent and bind it to libraries so it can use RAG for answering questions."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Create the agent",
                "tool": "agentbase_create_agent",
                "params": {
                    "name": "My Agent",
                    "system_prompt": "You are a helpful assistant...",
                    "model_provider": "ollama",
                    "model_name": "llama3",
                },
                "notes": "Set use_rag=True (default) for knowledge access.",
            },
            {
                "step": 2,
                "action": "Bind a library to the agent (preferred)",
                "tool": "agentbase_bind_knowledge_base",
                "params": {
                    "agent_id": "<from step 1>",
                    "library_id": "<your library>",
                },
                "notes": "Library binding is preferred over source binding. Agent searches all sources in the library.",
            },
            {
                "step": 3,
                "action": "Verify bindings",
                "tool": "agentbase_list_agent_knowledge_bases",
                "params": {"agent_id": "<from step 1>"},
            },
        ],
    },
    "monitor_sources": {
        "title": "Monitor and maintain sources",
        "description": (
            "Check system health, refresh stale content, retry failures, and manage file watchers."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Get system-wide analytics",
                "tool": "agentbase_get_source_analytics",
                "notes": "Shows total sources, documents, chunks, embedding distribution, Qdrant health.",
            },
            {
                "step": 2,
                "action": "Check indexing queue",
                "tool": "agentbase_get_indexing_queue",
                "notes": "Shows active and queued indexing jobs.",
            },
            {
                "step": 3,
                "action": "Refresh a source (re-index)",
                "tool": "agentbase_refresh_source",
                "params": {"source_id": "<source to refresh>"},
                "notes": "mode='full' (default) clears and re-indexes. mode='selective' with urls for specific pages.",
            },
            {
                "step": 4,
                "action": "Retry failed URLs only",
                "tool": "agentbase_retry_failed_urls",
                "params": {"source_id": "<source with failures>"},
                "notes": "Only for URL sources. Retries just the failed pages instead of a full refresh.",
            },
            {
                "step": 5,
                "action": "Start a file watcher for auto-sync",
                "tool": "agentbase_start_watcher",
                "params": {"source_id": "<directory source>"},
                "notes": "Only for directory sources. Auto-detects file changes and re-indexes.",
            },
            {
                "step": 6,
                "action": "Check all watcher statuses",
                "tool": "agentbase_get_watcher_statuses",
            },
        ],
    },
    "first_time_setup": {
        "title": "Getting started with Agentbase",
        "description": (
            "First-time setup: create an API key, explore what's available, then build your first library."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Bootstrap an API key (if none exist)",
                "tool": "agentbase_bootstrap_api_key",
                "notes": "Only works when no API keys exist. Store the returned key securely.",
            },
            {
                "step": 2,
                "action": "Check what's already in the system",
                "tool": "agentbase_get_source_analytics",
                "notes": "Shows existing sources, libraries, and system health at a glance.",
            },
            {
                "step": 3,
                "action": "List existing sources",
                "tool": "agentbase_list_sources",
            },
            {
                "step": 4,
                "action": "List existing libraries",
                "tool": "agentbase_list_libraries",
            },
            {
                "step": 5,
                "action": "Follow 'build_web_library' or 'build_file_library' workflow",
                "tool": "agentbase_get_workflow_guide",
                "params": {"goal": "build a knowledge library"},
                "notes": "Use this guide tool to get step-by-step instructions for your specific goal.",
            },
        ],
    },
    "assess_coverage": {
        "title": "Assess library coverage and find gaps",
        "description": (
            "Check which taxonomy terms have deep, adequate, thin, or no coverage "
            "in a library. Use this to decide where to add more sources."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Check library has a linked taxonomy",
                "tool": "agentbase_get_library",
                "params": {"library_id": "<your library>"},
                "notes": "Look for taxonomy_id in the response. If null, set up a taxonomy first (see setup_taxonomy workflow).",
            },
            {
                "step": 2,
                "action": "Run coverage analysis",
                "tool": "agentbase_get_library_coverage",
                "params": {"library_id": "<your library>"},
                "notes": "Returns per-term chunk counts and ratings: deep (>=20), adequate (>=10), thin (>=1), none (0).",
            },
            {
                "step": 3,
                "action": "Find additional sources to fill gap areas (thin/none terms)",
                "tool": "agentbase_create_source",
                "notes": (
                    "Create new sources targeting gap areas. Focus on terms rated 'thin' or 'none'. "
                    "Index them and add to the library."
                ),
            },
            {
                "step": 4,
                "action": "Re-assess after adding content",
                "tool": "agentbase_get_library_coverage",
                "params": {"library_id": "<your library>"},
                "notes": "Repeat until coverage meets your quality bar.",
            },
        ],
    },
    "maintain_library": {
        "title": "Maintain and refresh a knowledge library",
        "description": (
            "Check for stale sources, trigger refreshes, and keep your library current. "
            "Uses freshness policies to manage source lifecycle."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Check for stale or aging sources",
                "tool": "agentbase_list_stale_sources",
                "params": {"library_id": "<your library>"},
                "notes": (
                    "Returns sources approaching or past staleness threshold. "
                    "Stale = past threshold. Aging = within 80% of threshold."
                ),
            },
            {
                "step": 2,
                "action": "Refresh stale sources",
                "tool": "agentbase_refresh_source",
                "params": {"source_id": "<stale source id>"},
                "notes": "For automatic policy sources, the scheduler handles this. For manual, you trigger it.",
            },
            {
                "step": 3,
                "action": "Poll until refresh completes",
                "tool": "agentbase_get_source_status",
                "params": {"source_id": "<source id>"},
                "notes": "Wait for status to return to 'indexed'.",
            },
            {
                "step": 4,
                "action": "Re-check coverage after refresh",
                "tool": "agentbase_get_library_coverage",
                "params": {"library_id": "<your library>"},
                "notes": "Verify coverage hasn't degraded. If a source removed pages, coverage may drop.",
            },
            {
                "step": 5,
                "action": "Review freshness policies",
                "tool": "agentbase_list_sources",
                "notes": (
                    "Review freshness_policy settings: "
                    "'none' for static reference (code books, archived manuals). "
                    "'automatic' for content with known update cycles (vendor docs). "
                    "'manual' for content that changes unpredictably (community forums)."
                ),
            },
        ],
    },
    "evaluate_and_experiment": {
        "title": "Evaluate quality and A/B test agent configurations",
        "description": (
            "Build a golden question set for a library, score retrieval or agent answers "
            "with a scorecard, then A/B test config changes as an experiment: compare "
            "against the agent's baseline and promote the winner."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Create a question set for the library",
                "tool": "agentbase_create_question_set",
                "params": {
                    "library_id": "<your library>",
                    "name": "Core Questions",
                    "description": "Golden questions covering the library's key topics",
                },
                "notes": "A library can own multiple question sets (e.g. smoke set vs. deep set).",
            },
            {
                "step": 2,
                "action": "Add questions manually, or draft them with an LLM",
                "tool": "agentbase_add_question",
                "params": {
                    "question_set_id": "<from step 1>",
                    "question_text": "How do I configure X?",
                    "expected_criteria": "Names the exact setting and its location",
                    "expected_document_ids": ["<document id that should be retrieved>"],
                },
                "notes": (
                    "expected_document_ids powers retrieval metrics (found@k, MRR); "
                    "expected_criteria powers the LLM judge. Alternatively call "
                    "agentbase_generate_questions to draft questions from library content in a "
                    "background job, then review/edit the drafts."
                ),
            },
            {
                "step": 3,
                "action": "Run a baseline scorecard",
                "tool": "agentbase_run_scorecard",
                "params": {
                    "target_type": "agent",
                    "target_id": "<agent id>",
                    "question_set_id": "<from step 1>",
                },
                "notes": (
                    "target_type 'library' grades retrieval only (fast, no LLM). "
                    "'agent' also grades full answers with an LLM judge. Runs in the "
                    "background — poll agentbase_get_eval_run with the returned run_id."
                ),
            },
            {
                "step": 4,
                "action": "Create an experiment with config overrides",
                "tool": "agentbase_create_experiment",
                "params": {
                    "library_id": "<your library>",
                    "agent_id": "<agent id>",
                    "name": "Wider retrieval",
                    "overrides": {"rag_top_k": 10, "temperature": 0.2},
                },
                "notes": (
                    "Override keys: system_prompt, model_provider, model_name, "
                    "temperature, rag_top_k. No reindexing happens — overrides apply "
                    "at query time only."
                ),
            },
            {
                "step": 5,
                "action": "Compare the experiment against the agent's baseline",
                "tool": "agentbase_compare_experiment",
                "params": {
                    "experiment_id": "<from step 4>",
                    "question_set_id": "<from step 1>",
                },
                "notes": (
                    "Enqueues TWO scorecard runs (baseline + experiment). Poll "
                    "agentbase_get_eval_run on both returned run ids until completed."
                ),
            },
            {
                "step": 6,
                "action": "Read the per-question verdict",
                "tool": "agentbase_get_comparison",
                "params": {
                    "baseline_run_id": "<from step 5>",
                    "experiment_run_id": "<from step 5>",
                },
                "notes": "Returns metric deltas and improved/unchanged/regressed per question.",
            },
            {
                "step": 7,
                "action": "Promote the experiment if it won",
                "tool": "agentbase_promote_experiment",
                "params": {"experiment_id": "<from step 4>"},
                "notes": (
                    "Writes the overrides into the agent's live config and marks the "
                    "experiment 'promoted'. Skip if the comparison showed no improvement."
                ),
            },
        ],
    },
    "external_agent_search": {
        "title": "Search knowledge as an external agent",
        "description": (
            "Discover the best knowledge library for your query and search it efficiently. "
            "Ideal for external AI agents connecting via MCP."
        ),
        "steps": [
            {
                "step": 1,
                "action": "Discover the best library for your query",
                "tool": "agentbase_discover_library",
                "params": {"query": "your question or topic"},
                "notes": "Returns ranked library recommendations with confidence scores and coverage highlights.",
            },
            {
                "step": 2,
                "action": "Search the recommended library",
                "tool": "agentbase_search_library",
                "params": {
                    "query": "your specific question",
                    "library_id": "<library_id from step 1>",
                    "method": "auto",
                },
                "notes": "Use method='auto' to let the system pick the best search strategy. Check refinement_hints in the response.",
            },
            {
                "step": 3,
                "action": "Refine with filters if results are broad",
                "tool": "agentbase_search_library",
                "params": {
                    "query": "your question",
                    "library_id": "<same library_id>",
                    "filters": {"platforms": ["<from refinement_hints>"]},
                },
                "notes": "Use available_filters from refinement_hints to narrow results. Filters AND across keys, OR within a key's list.",
            },
            {
                "step": 4,
                "action": "Try deep search for complex multi-part questions",
                "tool": "agentbase_search_library",
                "params": {
                    "query": "complex multi-part question",
                    "library_id": "<same library_id>",
                    "method": "deep_search",
                },
                "notes": (
                    "Deep search decomposes complex questions into sub-queries. Use when initial results "
                    "don't fully answer the question. After retrieving results, synthesize them into your "
                    "response using content, source citations, and metadata for attribution."
                ),
            },
        ],
    },
}

# Build keyword index for fuzzy matching goals to recipes
_KEYWORD_MAP: dict[str, list[str]] = {
    "build_web_library": [
        "web", "website", "url", "documentation", "docs", "scrape",
        "crawl", "index web", "library from web", "knowledge library",
        "build library", "create library",
    ],
    "build_file_library": [
        "file", "files", "directory", "folder", "pdf", "docx", "upload",
        "local", "index files", "library from files",
    ],
    "create_sub_source": [
        "sub-source", "subsource", "sub source", "child source", "narrow",
        "scope", "scope to folder", "subtree", "view over folder",
        "filtered source", "filter to subfolder", "path prefix",
    ],
    "setup_taxonomy": [
        "taxonomy", "classification", "classify", "categorize", "facet",
        "term", "enrich", "enrichment", "tag", "label",
    ],
    "search_content": [
        "search", "query", "find", "lookup", "retrieve", "rag",
        "semantic", "hybrid", "filter", "deep search",
    ],
    "configure_agent": [
        "agent", "create agent", "configure agent", "bind", "knowledge",
        "rag agent", "ai agent", "chatbot",
    ],
    "monitor_sources": [
        "monitor", "health", "analytics", "refresh", "retry", "watcher",
        "maintenance", "status", "queue", "failed",
    ],
    "first_time_setup": [
        "start", "setup", "getting started", "first time", "bootstrap",
        "new", "begin", "onboard", "api key", "overview",
    ],
    "assess_coverage": [
        "coverage", "gap", "gaps", "thin", "assess", "check coverage",
        "what's missing", "coverage report", "taxonomy coverage",
    ],
    "maintain_library": [
        "maintain", "stale", "refresh", "update library", "keep current",
        "freshness", "aging", "out of date", "needs review",
    ],
    "evaluate_and_experiment": [
        "evaluate", "evaluation", "experiment", "a/b test", "ab test",
        "scorecard", "question set", "golden questions", "baseline",
        "compare", "promote", "judge", "quality", "regression", "tune",
        "temperature", "rag_top_k", "test agent",
    ],
    "external_agent_search": [
        "external", "agent", "discover", "discovery", "find library",
        "which library", "search library", "mcp search",
        "external agent", "automated search",
    ],
}


def _match_workflows(goal: str) -> list[str]:
    """Match a goal string to workflow keys by keyword overlap."""
    goal_lower = goal.lower()
    scores: list[tuple[str, int]] = []
    for key, keywords in _KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in goal_lower)
        if score > 0:
            scores.append((key, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [key for key, _ in scores]


@mcp.tool(
    description=(
        "Get workflow recipes for common goals. "
        "Pass a goal like 'build a knowledge library from web sources' "
        "or 'set up taxonomy classification' and get step-by-step tool sequences. "
        "Call with no goal to list all available workflows."
    ),
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def agentbase_get_workflow_guide(goal: str = "") -> dict:
    """Return workflow recipes matching a stated goal."""
    if not goal.strip():
        # Return the catalog
        return {
            "available_workflows": [
                {"key": key, "title": wf["title"], "description": wf["description"]}
                for key, wf in WORKFLOWS.items()
            ],
            "usage": "Call agentbase_get_workflow_guide with a goal to get step-by-step instructions.",
        }

    # Check for exact key match first
    if goal.strip() in WORKFLOWS:
        wf = WORKFLOWS[goal.strip()]
        return {"workflow": wf, "matched_by": "exact_key"}

    # Fuzzy keyword matching
    matches = _match_workflows(goal)
    if not matches:
        return {
            "error": "No matching workflow found.",
            "suggestion": "Try one of these goals or call with no goal to see all options.",
            "available_workflows": [
                {"key": key, "title": wf["title"]}
                for key, wf in WORKFLOWS.items()
            ],
        }

    # Return best match, mention others
    best = matches[0]
    result: dict = {
        "workflow": WORKFLOWS[best],
        "matched_by": "keyword",
    }
    if len(matches) > 1:
        result["related_workflows"] = [
            {"key": key, "title": WORKFLOWS[key]["title"]}
            for key in matches[1:3]  # Show up to 2 related
        ]

    return result
