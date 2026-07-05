/**
 * Test Studio types
 */

export interface TestSuite {
  id: string;
  project_id: string;
  prompt_id: string | null;
  name: string;
  description: string | null;
  test_case_count: number;
  last_run_at: string | null;
  last_run_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface TestSuiteCreate {
  name: string;
  project_id: string;
  prompt_id?: string;
  description?: string;
}

export interface TestSuiteUpdate {
  name?: string;
  description?: string;
  prompt_id?: string;
}

export interface TestCase {
  id: string;
  suite_id: string;
  name: string;
  input_text: string;
  expected_output: string | null;
  evaluation_criteria: string | null;
  expected_sources: string[] | null;
  tags: string[] | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface TestCaseCreate {
  suite_id: string;
  name: string;
  input_text: string;
  expected_output?: string;
  evaluation_criteria?: string;
  expected_sources?: string[];
  tags?: string[];
}

export interface TestCaseUpdate {
  name?: string;
  input_text?: string;
  expected_output?: string;
  evaluation_criteria?: string;
  expected_sources?: string[];
  tags?: string[];
  sort_order?: number;
}

export interface TestRun {
  id: string;
  suite_id: string;
  provider: string;
  model: string;
  status: string;
  overall_score: number | null;
  relevance_score: number | null;
  accuracy_score: number | null;
  retrieval_score: number | null;
  evaluator_provider: string | null;
  evaluator_model: string | null;
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TestCaseResult {
  id: string;
  run_id: string;
  test_case_id: string;
  test_case_name: string;
  input_text: string;
  expected_output: string | null;
  actual_output: string | null;
  passed: boolean | null;
  relevance_score: number | null;
  accuracy_score: number | null;
  retrieval_score: number | null;
  retrieved_sources: string[] | null;
  evaluation_notes: string | null;
  latency_ms: number | null;
  tokens_used: number | null;
  created_at: string;
}

// SSE events for test execution
export interface TestStreamStartEvent {
  run_id: string;
  total_cases: number;
}

export interface TestStreamCaseStartEvent {
  case_id: string;
  case_name: string;
  index: number;
}

export interface TestStreamCaseCompleteEvent {
  case_id: string;
  passed: boolean | null;
  relevance_score: number | null;
  accuracy_score: number | null;
  retrieval_score: number | null;
  actual_output: string | null;
  latency_ms: number | null;
}

export interface TestStreamCompleteEvent {
  run_id: string;
  overall_score: number | null;
  relevance_score: number | null;
  accuracy_score: number | null;
  retrieval_score: number | null;
  passed_cases: number;
  failed_cases: number;
}

export interface TestStreamCallbacks {
  onStart?: (data: TestStreamStartEvent) => void;
  onCaseStart?: (data: TestStreamCaseStartEvent) => void;
  onCaseComplete?: (data: TestStreamCaseCompleteEvent) => void;
  onComplete?: (data: TestStreamCompleteEvent) => void;
  onError?: (data: { message: string }) => void;
}
