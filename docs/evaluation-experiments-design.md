# Evaluation & Experiments — Design

**Date:** 2026-06-11
**Status:** Approved design, pre-implementation
**Supersedes/absorbs:** #42 (test service), #44 (retrieval benchmarks), #54 (Experiments page)

---

## 1. Problem & Vision

Agentbase's founding thesis includes letting users test combinations of chunking
strategies, embedding models, retrieval methods, and prompting strategies. Today
that capability is fragmented across three half-built pieces:

- **#54** — a source-scoped A/B workbench (backend done, UI broken) that compares
  raw chunk lists with no way to declare a winner.
- **#44** — a proposal for retrieval benchmarks (precision@k, nDCG, MRR) living in
  scripts and docs, outside the product.
- **#42** — a test harness (`TestSuite`/`TestCase`/`TestRun`/`TestCaseResult`
  models, `test_service.py`, `api/tests.py`) that exists but is anchored to the
  deprecated `Project` entity and has no UI.

The user's real question is never "which config is better?" — it is **"can I
trust my agent's answers, and if not, what do I change?"** This design unifies
the three issues into one feature, **Evaluation**, with the **Library as the
center of gravity** (libraries are where real queries run — agent queries,
library chat, and `search_library` all hit library collections; sources are
ingestion plumbing).

Core loop:

1. **Capture what "good" looks like** — golden question sets per library
   (generated from library content, human-curated).
2. **Score what exists** — baseline scorecard for a library or agent.
3. **Change one thing, get a verdict** — experiments with config overrides,
   compared per-question against baseline ("41 improved or unchanged, 4
   regressed").
4. **Promote with evidence** — winning config becomes the live config; the
   question set keeps running as a regression alarm.

**Two first-class interfaces:** the UI for humans and MCP tools for agents. An
agent must be able to run the entire tuning loop autonomously — generate
questions, baseline, experiment, compare, promote.

---

## 2. Concepts & Data Model

Four entities. New `eval_*` tables replace the unused project-anchored `test_*`
tables (single migration; verify tables are empty before dropping).

### QuestionSet (owned by a Library)

| Field | Notes |
|-------|-------|
| `id`, `library_id` (FK, CASCADE), `name`, `description` | |
| `created_at`, `updated_at` | |

### Question (golden test case)

| Field | Notes |
|-------|-------|
| `question_set_id` (FK, CASCADE) | |
| `question_text` | What a user would ask |
| `expected_criteria` | Free-text facts a good answer must contain — what the LLM judge grades against |
| `expected_document_ids` | JSON list of `documents.id` — ground truth for objective retrieval metrics |
| `tags` | JSON list, for slicing scorecards |
| `origin` | `generated` \| `manual` |
| `status` | `draft` \| `active` \| `archived` \| `stale` — only `active` questions score |

Lifecycle rules: a question that has EvalResults can only be **archived**, never
deleted (FK `ondelete=RESTRICT`; service converts delete→archive) — deleting it
would destroy scorecard history. If any of a question's `expected_document_ids`
no longer exist (document removed from the library), the next run marks the
question `stale`: excluded from scoring, surfaced in the curation queue for
re-pointing — never silently scored as 0%.

### EvalRun (a scorecard)

| Field | Notes |
|-------|-------|
| `target_type` | `library` \| `agent` \| `experiment` |
| `target_id` | Polymorphic reference (no DB-level FK) |
| `target_label` | Denormalized display name snapshot — runs stay readable after their target (e.g. a deleted experiment) is gone; lookups are null-tolerant |
| `question_set_id` (FK) | |
| `config_snapshot` | JSON — full effective config at run time, so old scorecards stay interpretable |
| `run_type` | `retrieval` (objective only) \| `answer` (retrieval + LLM judge) |
| `status` | `pending` \| `running` \| `completed` \| `partial` \| `error` |
| `metrics_summary` | JSON — aggregates: found@5, found@10, MRR, judge-score means, latency p50/p95 |
| `started_at`, `finished_at` | |

### EvalResult (one question's grade in a run)

| Field | Notes |
|-------|-------|
| `eval_run_id` (FK, CASCADE), `question_id` (FK) | |
| `retrieved` | JSON — doc ids + ranks + scores as retrieved |
| `retrieval_metrics` | JSON — expected-doc hit@k, best rank |
| `answer_text` | Agent runs only |
| `judge_scores` | JSON — relevance, accuracy, groundedness (0–1); null if not judged |
| `judge_rationale` | Judge model's explanation, for drill-down |
| `passed` | Derived boolean for quick verdicts |
| `latency_ms` | |

### Experiment (rework of `ExperimentalIndex`)

| Field | Notes |
|-------|-------|
| `library_id` (FK, CASCADE) | **Library-scoped, not source-scoped** |
| `agent_id` (FK, nullable) | Required only for pipeline experiments whose overrides include prompt/model/temperature — identifies whose pipeline runs the answers |
| `name`, `description` | |
| `experiment_type` | `index` \| `pipeline` |
| `overrides` | JSON — index: chunk_size, chunk_overlap, chunking_strategy, embedding_provider/model; pipeline: top_k, hybrid, reranker, prompt_id, model, temperature |
| `shadow_collection` | Qdrant collection name (index type only) |
| `status` | `pending` \| `indexing` \| `ready` \| `promoted` \| `error` |
| `created_at`, `promoted_at` | |

---

## 3. Question Set Lifecycle: Generate → Curate → Trust

The adoption-critical flow. Writing 50 questions by hand is homework nobody
does; the system drafts them, the human stays the judge.

1. **Generate** — "Generate Questions" on a library enqueues a background job
   (existing Job queue). The generator samples documents **across the library's
   taxonomy/enrichment coverage** (not just the first N docs), and drafts
   `question_text` + `expected_criteria` + `expected_document_ids` per candidate.
   The generation prompt is a new Prompt Studio task type (`question_generation`)
   so users can tune drafting style.
2. **Curate** — drafts land in a curation queue (same interaction pattern as
   taxonomy suggestions): approve / edit / discard. Only approved questions
   become `active`.
3. **Manual** — a form that creates `active` questions directly, skipping the
   queue. (Future, out of scope for v1: capture from real agent traffic.)

---

## 4. Scoring Engine

One engine, two depths. Both run questions **exactly as production queries run**
(library collection, production retrieval path).

- **Retrieval scoring** (objective, no LLM): for each active question, search the
  target collection; grade expected-doc found@5/found@10, best rank; aggregate
  MRR, latency p50/p95. This is #44's metrics engine with
  `expected_document_ids` as ground truth. Fast and free — runs on every
  experiment automatically.
- **Answer scoring** (LLM judge): for agent-level runs, generate the full answer
  through the agent's pipeline (prompt + model + retrieval), then an evaluator
  model grades it against `expected_criteria` → relevance, accuracy,
  groundedness + rationale. Evaluator model = new `ModelAssignment` task type
  (`evaluation`), swappable in Providers. Judge prompt = Prompt Studio task type
  (`answer_evaluation`). Reuses the judging logic already in `test_service.py`.

A scorecard renders as a report card: overall grade, per-metric breakdown,
sortable per-question table, drill-down to retrieved chunks / judged answer /
judge rationale. Runs persist, giving each library a **quality history** —
re-index a source, re-run, see regressions before users do. (#44's
"results in `docs/benchmark_results/`" becomes DB rows, exportable as JSON.)

**Precision/recall note:** with one-to-few expected docs per question, found@k
and MRR are the honest metrics; full precision@k/recall@k from #44 require
graded relevance labels and are deferred until question sets support
multi-document relevance grades (future enhancement, schema allows it via
`expected_document_ids` list).

---

## 5. Experiments

Create: pick a library → pick overrides → pick a question set.

- **Pipeline experiment** (instant): query-time overrides only (top_k, hybrid,
  reranker; for agent-level: prompt, model, temperature). No indexing; runs
  against the live collection with overridden settings.
- **Index experiment** (minutes): background job re-chunks **every bound
  source** of the library from stored `document_content.raw_content` into a
  shadow Qdrant collection with the experimental chunking/embedding config.
  **No re-ingestion ever** — re-embedding cost only. Progress via SSE, like
  indexing today. Structural chunking strategies apply where document structure
  survived extraction (headings/sections present in `raw_content`); flattened
  documents fall back to recursive splitting.

**Compare** = two EvalRuns (baseline vs. experiment) over the same question set,
diffed per question: improved / regressed / unchanged + aggregate verdict.
Improvement = retrieval-metric delta (rank improved, found where missing) and/or
judge-score delta beyond a small threshold (default 0.1, configurable).

**Promote:**
- Index type → the library points at the shadow collection (**shadow becomes
  live** — no second rebuild), experimental config persists as the library's
  indexing defaults (new library-level fields: `chunk_size`, `chunk_overlap`,
  `chunking_strategy`, `embedding_provider`, `embedding_model` — these become
  the config future source bindings index with), old collection deleted after
  swap. Promotion blocked if the experiment status is not `ready`.
- Pipeline type → overrides written into library retrieval settings / agent
  config.

**Delete** drops the shadow collection and the experiment row (EvalRuns persist
for history — their `config_snapshot` + `target_label` keep them readable after
the experiment is gone).

**Swap ordering (no split-brain):** promote commits the Postgres pointer change
to the shadow collection *first*; only after commit is the old collection
deleted. A failure mid-promote can leave an orphaned old collection (harmless,
reclaimed by cleanup) but never a library pointing at a missing collection. A
maintenance task garbage-collects Qdrant collections with no matching library or
experiment row (also covers shadow collections from failed/aborted experiments).

**Cost preview:** before an index experiment starts, the create response/dialog
shows document count and estimated chunk count for the library, so re-embedding
cost (API-billed providers) or time (local Ollama) is visible before committing.

**Presets:** #44's proposed experiments ship as one-click presets — "Structural
chunking", "Contextual embeddings" (prepend title/category to chunks),
"Native Qdrant RRF", "Reranker pass", "Multi-stage retrieval (broad → rerank →
top-k)".

---

## 6. UI (human interface)

Top-level nav entry **Experiments** (standing product decision), three tabs:

| Tab | Contents |
|-----|----------|
| **Question Sets** | Per-library sets, generation wizard, curation queue, manual editor |
| **Scorecards** | Run baseline (library or agent), report card, quality history/trend |
| **Experiments** | Create (library + knobs + question set), status board, comparison verdict view, promote/delete with confirmation |

Secondary entry points: **Quality tab on Agent detail** (latest scorecard, link
to Experiments page); **Questions link on Library detail**. shadcn/ui; status
colors via `--status-*` tokens; toasts for action outcomes; ErrorBanner for
page-load failures; URL params for filter state (house patterns).
Improved/regressed/unchanged verdicts pair color with icons + text labels
(accessibility — never color alone); scorecard drill-downs use collapsible
panels so the per-question detail view works on narrow viewports.

---

## 7. MCP Interface (agent interface)

Everything the UI can do, an agent can do. New `evaluation` tool module on the
MCP server, mirroring the REST endpoints (same service layer underneath — both
interfaces are thin clients). **Every mutating tool enforces `Scope.WRITE`** —
that includes `create_question_set`, `generate_questions`, `add_question`,
`update_question`, `delete_question`, `run_scorecard` (creates runs + consumes
compute), `create_experiment`, `promote_experiment`, and `delete_experiment` —
matching the existing convention that read-only tools alone are READ-scoped.

| Tool | Purpose |
|------|---------|
| `list_question_sets` / `get_question_set` | Browse sets + questions for a library |
| `create_question_set` | Create an empty set |
| `generate_questions` | Enqueue generation job for a library/set |
| `add_question` / `update_question` / `delete_question` | Manual authoring + curation (approve = status→active) |
| `run_scorecard` | Run a question set against library / agent / experiment; returns run id |
| `get_eval_run` / `list_eval_runs` | Scorecard results, per-question drill-down, history |
| `create_experiment` | Library + type + overrides (presets addressable by name) |
| `list_experiments` / `get_experiment` | Status, config, shadow-index progress |
| `compare_experiment` | Baseline-vs-experiment verdict over a question set |
| `promote_experiment` | Swap winner live (WRITE scope) |
| `delete_experiment` | Drop shadow collection + record (WRITE scope) |

The MCP `guide` tool gains an **evaluation workflow chapter** describing the
loop (generate → curate → baseline → experiment → compare → promote) so agents
discover the capability. The `knowledge-librarian` skill gets a tuning recipe
that uses these tools — making autonomous library tuning a documented workflow.

Long-running operations (generation, shadow indexing, scorecard runs) return
job/run ids immediately; agents poll `get_eval_run` / `get_experiment` for
completion (consistent with existing `index_source` / `get_indexing_queue`
patterns).

---

## 8. REST API Sketch

```
/api/evaluation/question-sets            GET (by ?library_id), POST
/api/evaluation/question-sets/{id}       GET, PATCH, DELETE
/api/evaluation/question-sets/{id}/generate   POST  (enqueue generation)
/api/evaluation/questions/{id}           PATCH, DELETE
/api/evaluation/runs                     GET (filters), POST (run scorecard)
/api/evaluation/runs/{id}                GET (summary + results)
/api/evaluation/runs/{id}/rejudge        POST (re-judge unjudged results of a partial run)
/api/experiments                         GET (?library_id), POST
/api/experiments/{id}                    GET, DELETE
/api/experiments/{id}/compare            POST (question_set_id) — POST because it executes eval runs (compute side effects), not a pure read
/api/experiments/{id}/promote            POST
```

`/api/experiments` keeps its path but switches to library scoping (the page
never worked, so there are no UI consumers to break; MCP had no experiment
tools). Old `/api/tests` router and `test_*` tables are removed in the same
release.

---

## 9. Failure Handling

- **Judge model unavailable** → run completes with retrieval metrics, answer
  grades null, status `partial`; the `rejudge` endpoint/MCP tool re-judges only
  unjudged results.
- **Stale ground truth** → expected documents validated at run start; questions
  referencing deleted documents become `stale` (excluded, queued for
  re-curation) rather than scoring 0%.
- **Generation without taxonomy** → if a library has no taxonomy or unclassified
  documents, question generation falls back to stratified random sampling across
  documents.
- **Index experiment document failures** → logged per-document (IndexingLog
  pattern); experiment `error` if wholesale failure; partial shadow indexes are
  never promotable.
- **Long jobs** → cancelable via Job queue; SSE progress events.
- **VRAM budget (Mac Studio)** → eval runs execute sequentially (one at a
  time); each run records embedding + judge models used so quality-per-VRAM
  comparisons (#44) are answerable from run history.
- **Promote safety** → confirmation in UI; in MCP it is WRITE-scoped and
  validates experiment status `ready`; old collection deleted only after the
  swap commits.

---

## 10. Issue Mapping & Migration

| Issue | Disposition |
|-------|-------------|
| #42 | Superseded in place: `test_*` models/service/router re-anchored Project→Library, renamed to `eval_*`/evaluation terms; streaming-run + judge logic survives |
| #44 | Becomes the scoring engine, metric definitions, and experiment presets; no separate script harness — the benchmark is the product |
| #54 | Page ships, library-scoped; `ExperimentService` shadow/compare/promote machinery survives source→library rework (also fixes stale `ScrapedContent` references) |

Migration: one Alembic migration — create `eval_*` + experiment changes, and
drop `test_*` unconditionally (the tables never had a UI; any rows are dev
artifacts — an empty-check assertion inside the migration would block automated
upgrades, so the drop is documented in release notes instead).
`ExperimentalIndex` rows likewise drop; the table is recreated as `experiments`.

---

## 11. Build Order (one feature, shipped in slices)

1. **Data model + question sets + generate/curate flow** — the asset everything
   else needs. (MCP: question-set tools.)
2. **Scoring engine + baseline scorecards** — standalone value: regression
   alarm. (MCP: run/get scorecard tools.)
3. **Pipeline experiments + compare + promote** — instant experiments first.
   (MCP: experiment tools.)
4. **Index experiments** — library-scoped shadow rebuild machinery.
5. **Agent scorecards + Quality tab + guide chapter + knowledge-librarian
   recipe** — full-pipeline grading and agent-facing discoverability.

Each slice lands UI + MCP together so the two interfaces never drift.

---

## 12. Testing

- Deterministic unit tests for metric computation (found@k, MRR, latency
  aggregation) — no LLM involved.
- Service tests with mocked judge/embedding providers (existing provider-mock
  patterns).
- API tests per router (house `pytest` conventions, run in Docker).
- Curation flow and comparison verdict covered by frontend build verification.
