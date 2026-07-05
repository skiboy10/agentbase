/**
 * Evaluation types (Slice 1: question sets + curation; Slice 2: scorecard runs;
 * Slice 3: pipeline experiments + compare + promote)
 */

export type QuestionStatus = 'draft' | 'active' | 'archived' | 'stale';
export type QuestionOrigin = 'generated' | 'manual';

export interface QuestionSet {
  id: string;
  library_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  /** Per-status question counts, e.g. { active: 12, draft: 3 } */
  question_counts: Record<string, number>;
}

export interface Question {
  id: string;
  question_set_id: string;
  question_text: string;
  expected_criteria: string | null;
  expected_document_ids: string[] | null;
  tags: string[] | null;
  origin: QuestionOrigin;
  status: QuestionStatus;
  created_at: string;
  updated_at: string;
}

export interface QuestionSetDetail extends QuestionSet {
  questions: Question[];
}

export interface QuestionSetCreate {
  library_id: string;
  name: string;
  description?: string;
}

export interface QuestionCreate {
  question_text: string;
  expected_criteria?: string;
  expected_document_ids?: string[];
  tags?: string[];
}

export interface QuestionUpdate {
  question_text?: string;
  expected_criteria?: string;
  expected_document_ids?: string[];
  tags?: string[];
  status?: QuestionStatus;
}

export interface GenerateQuestionsRequest {
  questions_per_doc?: number;
  doc_sample_size?: number;
  /** Total draft questions to generate (5-50, default 30). Overrides doc_sample_size. */
  count?: number;
}

export interface GenerateQuestionsResponse {
  job_id: string;
  status: string;
}

// ---- Slice 2: scorecard runs ----

export type EvalTargetType = 'library' | 'agent';
export type EvalRunType = 'retrieval' | 'answer';
export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'partial' | 'error';

/** Per-question retrieval grades (null when the question has no expected docs). */
export interface RetrievalMetrics {
  found_at_5: boolean;
  found_at_10: boolean;
  best_rank: number | null;
  reciprocal_rank: number;
}

/** LLM judge dimension scores, each 0.0-1.0. */
export interface JudgeScores {
  relevance: number;
  accuracy: number;
  groundedness: number;
}

/** Aggregate metrics for a run (rates are 0-1 fractions; null when unscored). */
export interface MetricsSummary {
  question_count: number;
  scored_retrieval_count: number;
  found_at_5_rate: number | null;
  found_at_10_rate: number | null;
  mrr: number | null;
  judged_count: number;
  passed_count: number;
  avg_judge_scores: JudgeScores | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  stale_questions: number;
}

/** One retrieved document, in rank order. */
export interface RetrievedDoc {
  /** Null when the chunk predates library-aware ingestion and path/url resolution also failed. */
  document_id: string | null;
  source_id: string | null;
  title: string | null;
  score: number | null;
}

export interface EvalResult {
  id: string;
  question_id: string;
  question_text: string;
  expected_criteria?: string | null;
  expected_document_ids?: string[] | null;
  retrieved: RetrievedDoc[] | null;
  retrieval_metrics: RetrievalMetrics | null;
  answer_text: string | null;
  judge_scores: JudgeScores | null;
  judge_rationale: string | null;
  passed: boolean | null;
  latency_ms: number | null;
}

export interface EvalRunSummary {
  id: string;
  target_type: EvalTargetType;
  target_id: string;
  target_label: string;
  question_set_id: string;
  question_set_name: string;
  run_type: EvalRunType;
  status: EvalRunStatus;
  metrics_summary: MetricsSummary | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface EvalRunDetail extends EvalRunSummary {
  results: EvalResult[];
}

export interface EvalRunCreate {
  target_type: EvalTargetType;
  target_id: string;
  question_set_id: string;
}

export interface EvalRunCreateResponse {
  run_id: string;
  status: string;
}

// ---- Slice 3: pipeline experiments ----

/** pending/indexing are Slice-4 index-experiment states; pipeline experiments are ready immediately. */
export type ExperimentStatus = 'pending' | 'indexing' | 'ready' | 'promoted' | 'error';
export type ExperimentType = 'pipeline' | 'index';

/** Keys = Agent column names verbatim — the exact fields promote writes back. */
export interface ExperimentOverrides {
  system_prompt?: string;
  model_provider?: string;
  model_name?: string;
  temperature?: number;
  rag_top_k?: number;
}

export const OVERRIDE_KEYS = [
  'system_prompt',
  'model_provider',
  'model_name',
  'temperature',
  'rag_top_k',
] as const;
export type OverrideKey = (typeof OVERRIDE_KEYS)[number];

export interface Experiment {
  id: string;
  library_id: string;
  agent_id: string | null;
  name: string;
  description: string | null;
  experiment_type: ExperimentType;
  overrides: ExperimentOverrides;
  status: ExperimentStatus;
  error_message: string | null;
  created_at: string;
  promoted_at: string | null;
}

export interface ExperimentCreate {
  library_id: string;
  agent_id: string;
  name: string;
  description?: string;
  overrides: ExperimentOverrides;
}

/** 202 response from POST /api/experiments/{id}/compare — two queued scorecard runs. */
export interface CompareStartResponse {
  baseline_run_id: string;
  experiment_run_id: string;
}

export type ComparisonQuestionVerdict = 'improved' | 'regressed' | 'unchanged' | 'uncomparable';

/** One side of a per-question comparison — the result dict as persisted on EvalResult. */
export interface ComparisonQuestionSide {
  question_id?: string;
  question_text?: string | null;
  judge_scores?: JudgeScores | null;
  passed?: boolean | null;
  retrieval_metrics?: RetrievalMetrics | null;
  latency_ms?: number | null;
}

export interface ComparisonQuestion {
  question_id: string;
  question_text: string | null;
  verdict: ComparisonQuestionVerdict;
  /** Null when the question ran on only one side (verdict "uncomparable"). */
  baseline: ComparisonQuestionSide | null;
  experiment: ComparisonQuestionSide | null;
}

/** Per-dimension judge-score deltas; a dimension is null when either side is unjudged. */
export interface JudgeScoreDeltas {
  relevance: number | null;
  accuracy: number | null;
  groundedness: number | null;
}

/** Aggregate deltas (experiment − baseline), null when either side is unscored. */
export interface ComparisonMetricDeltas {
  found_at_5_rate?: number | null;
  found_at_10_rate?: number | null;
  mrr?: number | null;
  avg_judge_scores?: JudgeScoreDeltas | null;
  latency_p50_ms?: number | null;
}

export interface ComparisonReport {
  verdict_counts: {
    improved: number;
    regressed: number;
    unchanged: number;
  };
  /** Questions present in only one run — excluded from verdict counts. */
  uncomparable: number;
  per_question: ComparisonQuestion[];
  metric_deltas: ComparisonMetricDeltas;
}
