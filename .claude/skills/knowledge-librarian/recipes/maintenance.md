# Recipe: Maintain — keep a library current

Goal: detect stale sources, refresh them, and confirm coverage didn't degrade. Curated
knowledge rots; freshness is a first-class part of curation.

## Freshness policy (set per source at ingestion)

- `none` — static reference that never changes (archived manuals, code books). No refresh.
- `automatic` — predictable update cadence (vendor docs, release notes). The background
  scheduler refreshes on `refresh_interval_days` / `next_refresh_at`.
- `manual` — changes unpredictably (community forums, evolving wikis). You trigger refresh.

Related Source fields: `freshness_policy`, `stale_after_days`, `refresh_interval_days`,
`next_refresh_at`.

## Steps

1. **Find stale/aging sources** — `agentbase_list_stale_sources { library_id }`.
   *Stale* = past `stale_after_days` threshold; *aging* = within 80% of it.
2. **Refresh** — `agentbase_refresh_source { source_id }`. `automatic` sources are handled
   by the scheduler; trigger `manual` ones yourself. For web sources with previously failed
   pages, `agentbase_retry_failed_urls { source_id }`.
3. **Poll to completion** — `agentbase_get_source_status { source_id }` until back to
   `indexed`.
4. **Re-check coverage** — `agentbase_get_library_coverage { library_id }`. A refresh that
   removed pages can *drop* coverage; if a term slipped to `thin`/`none`, go to
   coverage-gap-analysis.md.
5. **Review policies periodically** — `agentbase_list_sources`; adjust `freshness_policy`
   as you learn each source's real volatility. Recompute rollups with
   `agentbase_recalculate_library_stats` if counts look off.

## Directory watchers (local sources)

For `directory` sources, file watchers keep content synced automatically:
`agentbase_get_watcher_statuses` / `agentbase_get_watcher_status`,
`agentbase_start_watcher` / `agentbase_stop_watcher`, `agentbase_force_sync_watcher`,
and `agentbase_list_watcher_events` to audit what changed.

## Notes

- After any refresh or re-enrich, re-run a representative search (agent-and-search.md) to
  confirm the library still answers its core questions.
- Maintenance loops back into Assess (phase 4) and Prove (phase 6) — a scheduled scorecard
  is the cleanest early-warning that quality has drifted.
