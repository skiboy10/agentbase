/**
 * Tests API
 */

import { apiFetch, createSSEStream } from './base';
import type {
  TestSuite,
  TestSuiteCreate,
  TestSuiteUpdate,
  TestCase,
  TestCaseCreate,
  TestCaseUpdate,
  TestRun,
  TestCaseResult,
  TestStreamStartEvent,
  TestStreamCaseStartEvent,
  TestStreamCaseCompleteEvent,
  TestStreamCompleteEvent,
  TestStreamCallbacks,
} from './types/tests';

export const testsApi = {
  // Suites
  listSuites: (projectId: string) =>
    apiFetch<TestSuite[]>(`/api/tests/suites?project_id=${projectId}`),

  getSuite: (id: string) =>
    apiFetch<TestSuite>(`/api/tests/suites/${id}`),

  createSuite: (data: TestSuiteCreate) =>
    apiFetch<TestSuite>('/api/tests/suites', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateSuite: (id: string, data: TestSuiteUpdate) =>
    apiFetch<TestSuite>(`/api/tests/suites/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteSuite: (id: string) =>
    apiFetch<null>(`/api/tests/suites/${id}`, { method: 'DELETE' }),

  // Cases
  listCases: (suiteId: string) =>
    apiFetch<TestCase[]>(`/api/tests/suites/${suiteId}/cases`),

  createCase: (data: TestCaseCreate) =>
    apiFetch<TestCase>('/api/tests/cases', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateCase: (id: string, data: TestCaseUpdate) =>
    apiFetch<TestCase>(`/api/tests/cases/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteCase: (id: string) =>
    apiFetch<null>(`/api/tests/cases/${id}`, { method: 'DELETE' }),

  // Execution
  runTests: (suiteId: string, provider: string, model: string, useRag: boolean = true) =>
    apiFetch<{ run_id: string; status: string }>(`/api/tests/suites/${suiteId}/run`, {
      method: 'POST',
      body: JSON.stringify({ provider, model, use_rag: useRag }),
    }),

  runTestsStream: (
    suiteId: string,
    provider: string,
    model: string,
    callbacks: TestStreamCallbacks,
    useRag: boolean = true,
    evaluatorProvider?: string,
    evaluatorModel?: string
  ): (() => void) => {
    const params = new URLSearchParams({
      provider,
      model,
      use_rag: String(useRag),
    });
    if (evaluatorProvider) params.set('evaluator_provider', evaluatorProvider);
    if (evaluatorModel) params.set('evaluator_model', evaluatorModel);

    return createSSEStream(
      `/api/tests/suites/${suiteId}/run/stream?${params}`,
      { method: 'GET' },
      (event) => {
        switch (event.type) {
          case 'start':
            callbacks.onStart?.(event.data as TestStreamStartEvent);
            break;
          case 'case_start':
            callbacks.onCaseStart?.(event.data as TestStreamCaseStartEvent);
            break;
          case 'case_complete':
            callbacks.onCaseComplete?.(event.data as TestStreamCaseCompleteEvent);
            break;
          case 'complete':
            callbacks.onComplete?.(event.data as TestStreamCompleteEvent);
            break;
          case 'error':
            callbacks.onError?.(event.data as { message: string });
            break;
        }
      }
    );
  },

  // Results
  getRun: (runId: string) =>
    apiFetch<TestRun>(`/api/tests/runs/${runId}`),

  getRunResults: (runId: string) =>
    apiFetch<TestCaseResult[]>(`/api/tests/runs/${runId}/results`),

  listRuns: (suiteId: string, limit: number = 20) =>
    apiFetch<TestRun[]>(`/api/tests/suites/${suiteId}/runs?limit=${limit}`),

  compareRuns: (runIds: string[]) =>
    apiFetch<{ runs: TestRun[]; case_comparisons: unknown[] }>('/api/tests/runs/compare', {
      method: 'POST',
      body: JSON.stringify(runIds),
    }),
};
