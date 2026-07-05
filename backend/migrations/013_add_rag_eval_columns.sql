-- Migration 013: Add RAG eval harness columns
-- Extends Test Studio with retrieval scoring and evaluator model override

ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS expected_sources TEXT;

ALTER TABLE test_case_results ADD COLUMN IF NOT EXISTS retrieved_sources TEXT;
ALTER TABLE test_case_results ADD COLUMN IF NOT EXISTS retrieval_score FLOAT;

ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS evaluator_provider VARCHAR(50);
ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS evaluator_model VARCHAR(100);
ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS retrieval_score FLOAT;
