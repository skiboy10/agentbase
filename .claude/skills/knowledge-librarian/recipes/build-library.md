# Recipe: Ingest — build a library from sources

Goal: turn the source plan into indexed, searchable content inside a library.

## A. Web / documentation source

1. **Create the source** — `agentbase_create_source`
   `{ name, source_type: "url", source_path: "https://docs.example.com" }`.
   Add `selected_urls` to limit to specific pages. Set `embedding_provider`/
   `embedding_model` if you have a preference; otherwise note the defaults for the
   library step.
2. **Index** — `agentbase_index_source { source_id }`. Background job; returns immediately.
3. **Poll to completion** — `agentbase_get_source_status { source_id }` until
   `status == "indexed"`. Watch `progress`/`progress_total` for %. Do not proceed while
   still `indexing`/`queued`.
4. **Create a library** — `agentbase_create_library`
   `{ name, embedding_provider: <MATCH source>, embedding_model: <MATCH source> }`.
   The embedding provider/model **must** match the source or search returns nothing.
5. **Attach the source** — `agentbase_add_source_to_library { library_id, source_id }`.
   Repeat for every source that belongs in this library.
6. **Verify** — `agentbase_search_sources { query: "<representative question>",
   knowledge_base_id: <library_id> }` (hybrid on by default). Confirm non-empty,
   on-topic chunks. **No passing search = library not built.**

## B. Local files / directory source

Same shape, differing at step 1:
- `agentbase_create_source { name, source_type: "file", source_path: "/path/to/doc.pdf" }`
  for a single file, or `source_type: "directory"` for a folder.
- Or upload bytes: `agentbase_upload_source_file` / `agentbase_upload_source_files`
  (base64), or `agentbase_add_files_to_source` to extend an existing source.
Then index → poll → create/attach to library → verify, as above.

## C. Sub-source (filtered view over an existing directory root)

When a large directory root is already indexed and you want to give an agent narrow
access to one slice (e.g. `ACME/Q4-Plan`) without re-indexing:
- Create a source scoped to the subfolder of the existing root. It shares the parent's
  watcher and chunks but only returns results from that subtree.
- Confirm the exact recipe with `agentbase_get_workflow_guide` goal
  `"create a sub-source over an existing directory root"`.

## Failure handling

- Indexing errored or partial → inspect status, then `agentbase_retry_failed_urls
  { source_id }` for web sources with failed pages.
- Source content changed at the origin → `agentbase_refresh_source` (see maintenance.md).
- Chunks look wrong / stale enrichment → `agentbase_re_enrich_source`.

## Notes

- A library is a Qdrant collection container and can hold many sources.
- Set each source's **freshness policy** now (`none` / `automatic` / `manual`) based on
  the volatility you noted during discovery — see maintenance.md.
