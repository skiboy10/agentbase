# Recipe: Prove — golden questions, scorecards, experiments

Goal: measure retrieval/answer quality with a golden question set, then A/B test config
changes and promote the winner. Turns curation from vibes into numbers.

## Steps

1. **Create a question set for the library** — `agentbase_create_question_set
   { library_id, name, description }`. A library can own several (e.g. smoke vs. deep).
   Seed it from the representative questions you wrote in source-discovery.md.
2. **Add questions** — `agentbase_add_question`
   `{ question_set_id, question_text, expected_criteria, expected_document_ids: [...] }`.
   - `expected_document_ids` → powers retrieval metrics (found@k, MRR).
   - `expected_criteria` → powers the LLM judge on full answers.
   Or draft in bulk: `agentbase_generate_questions` (background job over library content),
   then review/edit the drafts with `agentbase_update_question` / `agentbase_delete_question`.
3. **Baseline scorecard** — `agentbase_run_scorecard
   { target_type: "agent", target_id: <agent_id>, question_set_id }`.
   - `target_type: "library"` → retrieval only (fast, no LLM).
   - `target_type: "agent"` → also grades full answers with an LLM judge.
   Background job — poll `agentbase_get_eval_run { run_id }` until complete.
4. **Create an experiment** — `agentbase_create_experiment
   { library_id, agent_id, name, overrides: { rag_top_k: 10, temperature: 0.2 } }`.
   Override keys: `system_prompt`, `model_provider`, `model_name`, `temperature`,
   `rag_top_k`. Overrides apply at query time only — **no reindexing**.
5. **Compare vs. baseline** — `agentbase_compare_experiment
   { experiment_id, question_set_id }`. Enqueues TWO runs (baseline + experiment); poll
   `agentbase_get_eval_run` on both returned run ids.
6. **Read the verdict** — `agentbase_get_comparison
   { baseline_run_id, experiment_run_id }`. Returns metric deltas and
   improved/unchanged/regressed per question.
7. **Promote if it won** — `agentbase_promote_experiment { experiment_id }`. Writes the
   overrides into the agent's live config. Skip if the comparison showed no improvement.

## Notes

- Re-grade an existing run after a judge/prompt change with `agentbase_rejudge_eval_run`.
- List/inspect history: `agentbase_list_question_sets`, `agentbase_get_question_set`,
  `agentbase_list_eval_runs`, `agentbase_list_experiments`, `agentbase_get_experiment`.
- Only pipeline-type experiments (config overrides) are live; index-type (shadow re-index)
  experiments are a future slice — see docs/evaluation-experiments-design.md.
