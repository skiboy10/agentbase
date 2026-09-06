# Recipe: Serve — bind an agent, and search as a client

Two related jobs: (A) wire a curated library into an Agentbase agent so it answers with
RAG, and (B) search the knowledge efficiently as an external agent.

## A. Configure an agent with knowledge access

1. **Create the agent** — `agentbase_create_agent`
   `{ name, system_prompt, model_provider: "ollama", model_name: "llama3" }`.
   Keep `use_rag=True` (default) for knowledge access.
   (For GPT-5+ models the repo convention is temperature 1 — see CLAUDE.md.)
2. **Bind the library (preferred over source-level binding)** —
   `agentbase_bind_knowledge_base { agent_id, library_id }`. The agent then searches all
   sources in the library. Repeat to bind multiple libraries.
3. **Verify bindings** — `agentbase_list_agent_knowledge_bases { agent_id }`.

Prefer library binding to per-source binding: it keeps the agent current as the library
gains sources.

## B. Search knowledge as an external agent

1. **Discover the best library** — `agentbase_discover_library { query }`. Returns ranked
   libraries with confidence scores and coverage highlights.
2. **Search it** — `agentbase_search_library { query, library_id, method: "auto" }`.
   `auto` lets the system pick the strategy. Read `refinement_hints` in the response.
3. **Refine with filters** if results are broad — `agentbase_search_library
   { query, library_id, filters: { platforms: ["<from refinement_hints>"] } }`.
   Filters **AND** across keys, **OR** within a key's list. Discover available filter keys
   via `refinement_hints`, or `agentbase_list_filter_fields` / `agentbase_list_filter_values`.
4. **Deep search for complex, multi-part questions** — `agentbase_search_library
   { query, library_id, method: "deep_search" }`. Decomposes into sub-queries; use when
   `auto` doesn't fully answer. Then synthesize results with content + source citations +
   metadata for attribution.

## Notes

- `agentbase_search_sources` (with `knowledge_base_id`) is the internal search used during
  curation/verification; `agentbase_search_library` + `agentbase_discover_library` are the
  client-facing entry points for external agents over MCP.
- Always attribute answers to source citations — that's the point of curated knowledge.
