"""Pure retrieval/aggregate metric computation. No I/O — unit-testable."""
from typing import Optional


def score_retrieval(retrieved_doc_ids: list[str],
                    expected_doc_ids: Optional[list[str]]) -> Optional[dict]:
    """Grade one question's retrieval. None when no expectation is set
    (question contributes no retrieval signal). best_rank is 1-based."""
    if not expected_doc_ids:
        return None
    expected = set(expected_doc_ids)
    best_rank = None
    for i, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in expected:
            best_rank = i
            break
    return {
        "found_at_5": best_rank is not None and best_rank <= 5,
        "found_at_10": best_rank is not None and best_rank <= 10,
        "best_rank": best_rank,
        "reciprocal_rank": (1.0 / best_rank) if best_rank else 0.0,
    }


def percentile(values: list, pct: float) -> Optional[float]:
    """Linear-interpolated percentile; None for empty input."""
    if not values:
        return None
    vals = sorted(values)
    k = (len(vals) - 1) * (pct / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    if lo == hi:
        return float(vals[lo])
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 4)


def aggregate_run_metrics(results: list[dict]) -> dict:
    """Aggregate per-question result dicts into a run's metrics_summary."""
    n = len(results)
    rm = [r["retrieval_metrics"] for r in results if r.get("retrieval_metrics")]
    judged = [r["judge_scores"] for r in results if r.get("judge_scores")]
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]

    avg_judge = None
    if judged:
        keys = ("relevance", "accuracy", "groundedness")
        avg_judge = {k: round(sum(j.get(k, 0.0) for j in judged) / len(judged), 4)
                     for k in keys}

    return {
        "question_count": n,
        "scored_retrieval_count": len(rm),
        "found_at_5_rate": round(sum(m["found_at_5"] for m in rm) / len(rm), 4) if rm else None,
        "found_at_10_rate": round(sum(m["found_at_10"] for m in rm) / len(rm), 4) if rm else None,
        "mrr": round(sum(m["reciprocal_rank"] for m in rm) / len(rm), 4) if rm else None,
        "judged_count": len(judged),
        "passed_count": sum(1 for r in results if r.get("passed") is True),
        "avg_judge_scores": avg_judge,
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
    }
