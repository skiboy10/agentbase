"""Deterministic tests for retrieval metric computation — no LLM, no DB."""
from app.services.evaluation.metrics import (
    score_retrieval, aggregate_run_metrics, percentile,
)


class TestScoreRetrieval:
    def test_expected_doc_at_rank_1(self):
        m = score_retrieval(retrieved_doc_ids=["d1", "d2", "d3"], expected_doc_ids=["d1"])
        assert m == {"found_at_5": True, "found_at_10": True, "best_rank": 1,
                     "reciprocal_rank": 1.0}

    def test_expected_doc_at_rank_7(self):
        retrieved = [f"d{i}" for i in range(1, 11)]
        m = score_retrieval(retrieved_doc_ids=retrieved, expected_doc_ids=["d7"])
        assert m["found_at_5"] is False
        assert m["found_at_10"] is True
        assert m["best_rank"] == 7
        assert abs(m["reciprocal_rank"] - 1/7) < 1e-9

    def test_not_found(self):
        m = score_retrieval(retrieved_doc_ids=["d1", "d2"], expected_doc_ids=["nope"])
        assert m == {"found_at_5": False, "found_at_10": False, "best_rank": None,
                     "reciprocal_rank": 0.0}

    def test_multiple_expected_uses_best(self):
        m = score_retrieval(retrieved_doc_ids=["a", "b", "c"], expected_doc_ids=["c", "b"])
        assert m["best_rank"] == 2  # earliest hit among expected

    def test_no_expectation_returns_none(self):
        assert score_retrieval(retrieved_doc_ids=["a"], expected_doc_ids=[]) is None
        assert score_retrieval(retrieved_doc_ids=["a"], expected_doc_ids=None) is None


class TestPercentile:
    def test_p50_p95(self):
        vals = list(range(1, 101))  # 1..100
        assert percentile(vals, 50) == 50.5
        assert percentile(vals, 95) == 95.05
        assert percentile([], 50) is None


class TestAggregate:
    def test_aggregates_over_results(self):
        results = [
            {"retrieval_metrics": {"found_at_5": True, "found_at_10": True,
                                   "best_rank": 1, "reciprocal_rank": 1.0},
             "judge_scores": {"relevance": 0.9, "accuracy": 0.8, "groundedness": 1.0},
             "passed": True, "latency_ms": 100},
            {"retrieval_metrics": {"found_at_5": False, "found_at_10": True,
                                   "best_rank": 8, "reciprocal_rank": 0.125},
             "judge_scores": None, "passed": None, "latency_ms": 300},
        ]
        agg = aggregate_run_metrics(results)
        assert agg["question_count"] == 2
        assert agg["found_at_5_rate"] == 0.5
        assert agg["found_at_10_rate"] == 1.0
        assert abs(agg["mrr"] - (1.0 + 0.125) / 2) < 1e-9
        assert agg["judged_count"] == 1
        assert agg["passed_count"] == 1
        assert agg["avg_judge_scores"] == {"relevance": 0.9, "accuracy": 0.8,
                                           "groundedness": 1.0}
        assert agg["latency_p50_ms"] == 200.0

    def test_handles_missing_retrieval_metrics(self):
        agg = aggregate_run_metrics([{"retrieval_metrics": None, "judge_scores": None,
                                      "passed": None, "latency_ms": None}])
        assert agg["question_count"] == 1
        assert agg["found_at_5_rate"] is None
        assert agg["mrr"] is None
