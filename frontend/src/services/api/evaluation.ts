/**
 * Evaluation API (Slice 1: question sets + curation; Slice 2: scorecard runs;
 * Slice 3: pipeline experiments + compare + promote)
 */

import { apiFetch } from './base';
import type {
  QuestionSet,
  QuestionSetDetail,
  QuestionSetCreate,
  Question,
  QuestionCreate,
  QuestionUpdate,
  GenerateQuestionsRequest,
  GenerateQuestionsResponse,
  EvalRunSummary,
  EvalRunDetail,
  EvalRunCreate,
  EvalRunCreateResponse,
  EvalTargetType,
  Experiment,
  ExperimentCreate,
  CompareStartResponse,
  ComparisonReport,
} from './types/evaluation';

export const evaluationApi = {
  // List question sets, optionally filtered by library
  listQuestionSets: (libraryId?: string) =>
    apiFetch<QuestionSet[]>(
      `/api/evaluation/question-sets${libraryId ? `?library_id=${libraryId}` : ''}`
    ),

  // Get a question set with all its questions
  getQuestionSet: (id: string) =>
    apiFetch<QuestionSetDetail>(`/api/evaluation/question-sets/${id}`),

  // Create a question set
  createQuestionSet: (data: QuestionSetCreate) =>
    apiFetch<QuestionSet>('/api/evaluation/question-sets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Update a question set (name / description)
  updateQuestionSet: (id: string, data: { name?: string; description?: string }) =>
    apiFetch<QuestionSet>(`/api/evaluation/question-sets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Delete a question set (and its questions)
  deleteQuestionSet: (id: string) =>
    apiFetch<void>(`/api/evaluation/question-sets/${id}`, { method: 'DELETE' }),

  // Add a manual question to a set (created active)
  addQuestion: (setId: string, data: QuestionCreate) =>
    apiFetch<Question>(`/api/evaluation/question-sets/${setId}/questions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Update a question (text, criteria, tags, status transitions)
  updateQuestion: (id: string, data: QuestionUpdate) =>
    apiFetch<Question>(`/api/evaluation/questions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Delete a question — archived instead if it already has eval results
  deleteQuestion: (id: string) =>
    apiFetch<{ outcome: 'deleted' | 'archived' }>(`/api/evaluation/questions/${id}`, {
      method: 'DELETE',
    }),

  // Enqueue background generation of draft questions from library documents
  generateQuestions: (setId: string, data: GenerateQuestionsRequest = {}) =>
    apiFetch<GenerateQuestionsResponse>(
      `/api/evaluation/question-sets/${setId}/generate`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),

  // ---- Slice 2: scorecard runs ----

  // List scorecard runs (newest first), optionally filtered
  listRuns: (params?: {
    target_type?: EvalTargetType;
    target_id?: string;
    question_set_id?: string;
    library_id?: string;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.target_type) query.set('target_type', params.target_type);
    if (params?.target_id) query.set('target_id', params.target_id);
    if (params?.question_set_id) query.set('question_set_id', params.question_set_id);
    if (params?.library_id) query.set('library_id', params.library_id);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return apiFetch<EvalRunSummary[]>(`/api/evaluation/runs${qs ? `?${qs}` : ''}`);
  },

  // Get a run with its per-question results
  getRun: (id: string) => apiFetch<EvalRunDetail>(`/api/evaluation/runs/${id}`),

  // Create + enqueue a scorecard run (202, completes in a background job)
  createRun: (data: EvalRunCreate) =>
    apiFetch<EvalRunCreateResponse>('/api/evaluation/runs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Re-judge unjudged results of a partial/completed answer run
  rejudgeRun: (id: string) =>
    apiFetch<EvalRunCreateResponse>(`/api/evaluation/runs/${id}/rejudge`, {
      method: 'POST',
    }),

  // ---- Slice 3: pipeline experiments ----

  // List experiments, optionally filtered by library and/or agent
  listExperiments: (params?: { library_id?: string; agent_id?: string }) => {
    const query = new URLSearchParams();
    if (params?.library_id) query.set('library_id', params.library_id);
    if (params?.agent_id) query.set('agent_id', params.agent_id);
    const qs = query.toString();
    return apiFetch<Experiment[]>(`/api/experiments${qs ? `?${qs}` : ''}`);
  },

  // Create a pipeline experiment (agent overrides, ready immediately — no reindex)
  createExperiment: (data: ExperimentCreate) =>
    apiFetch<Experiment>('/api/experiments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Get one experiment
  getExperiment: (id: string) => apiFetch<Experiment>(`/api/experiments/${id}`),

  // Delete an experiment (its EvalRuns persist for history)
  deleteExperiment: (id: string) =>
    apiFetch<void>(`/api/experiments/${id}`, { method: 'DELETE' }),

  // Start a comparison: enqueues baseline + experiment scorecard runs (202)
  compareExperiment: (id: string, questionSetId: string) =>
    apiFetch<CompareStartResponse>(`/api/experiments/${id}/compare`, {
      method: 'POST',
      body: JSON.stringify({ question_set_id: questionSetId }),
    }),

  // Fetch the per-question verdict once both runs are completed/partial
  getComparison: (id: string, baselineRunId: string, experimentRunId: string) =>
    apiFetch<ComparisonReport>(
      `/api/experiments/${id}/comparison?baseline_run_id=${baselineRunId}&experiment_run_id=${experimentRunId}`
    ),

  // Promote: write the experiment's overrides into the agent's live config
  promoteExperiment: (id: string) =>
    apiFetch<Experiment>(`/api/experiments/${id}/promote`, { method: 'POST' }),
};
