# Recipe: Orient (first-time setup)

Goal: know what already exists before building anything. Prevents duplicate sources
and tells you which embedding settings are already in play.

## Steps

1. **Bootstrap an API key** (only if none exist yet) — `agentbase_bootstrap_api_key`.
   Works exactly once, when the system has no keys. Store the returned key securely;
   it is shown only once.
2. **Snapshot system health** — `agentbase_get_source_analytics`. Shows existing
   sources, libraries, and health at a glance.
3. **List existing sources** — `agentbase_list_sources`. Note each source's
   `embedding_provider`/`embedding_model` and `status`; reuse before re-creating.
4. **List existing libraries** — `agentbase_list_libraries`. See what's already
   assembled and which taxonomies are linked.
5. **Pick the workflow** — `agentbase_get_workflow_guide` with your concrete goal to
   get the current step-by-step tool sequence.

## Notes

- Reuse beats recreate: an already-indexed source can be added to a new library with
  `agentbase_add_source_to_library` — no re-indexing needed.
- Capture the prevailing embedding provider/model here; you will need to match it when
  you create a library.
