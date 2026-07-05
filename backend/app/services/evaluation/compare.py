"""Comparison verdict engine (design doc §4).

Pure functions: classify one question's baseline-vs-experiment delta and
aggregate two runs into a verdict report. Conservative rule: ANY regression
signal (judge mean down past threshold, passed True→False, found@10 lost,
best_rank worse) classifies the question as regressed, even when other
signals improved.

Plus orchestration: start_comparison enqueues the baseline + experiment run
pair; load_comparison builds the verdict JSON from two finished runs.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Experiment
from app.services.evaluation.metrics import aggregate_run_metrics

# Judge-score mean delta (relevance/accuracy/groundedness) beyond this
# threshold flags improvement/regression; within it the judge signal is noise.
JUDGE_DELTA_THRESHOLD = 0.1

JUDGE_KEYS = ("relevance", "accuracy", "groundedness")


def _judge_mean(judge_scores: Optional[dict]) -> Optional[float]:
    if not judge_scores:
        return None
    vals = [judge_scores.get(k) for k in JUDGE_KEYS]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def classify_question_delta(baseline: Optional[dict],
                            experiment: Optional[dict]) -> str:
    """Verdict for one question: improved | regressed | unchanged | uncomparable.

    Inputs are per-question result dicts with keys judge_scores, passed,
    retrieval_metrics (as persisted on EvalResult). A question present in
    only one run is uncomparable.
    """
    if baseline is None or experiment is None:
        return "uncomparable"
    improved = False
    regressed = False

    # Judge-score mean delta
    b_mean = _judge_mean(baseline.get("judge_scores"))
    e_mean = _judge_mean(experiment.get("judge_scores"))
    if b_mean is not None and e_mean is not None:
        delta = e_mean - b_mean
        if delta > JUDGE_DELTA_THRESHOLD:
            improved = True
        elif delta < -JUDGE_DELTA_THRESHOLD:
            regressed = True

    # Passed flip (overrides a small judge delta)
    b_passed, e_passed = baseline.get("passed"), experiment.get("passed")
    if b_passed is not None and e_passed is not None and b_passed != e_passed:
        if e_passed:
            improved = True
        else:
            regressed = True

    # Retrieval changes: found@10 flip / best_rank change
    b_retr = baseline.get("retrieval_metrics")
    e_retr = experiment.get("retrieval_metrics")
    if b_retr and e_retr:
        b_found, e_found = b_retr.get("found_at_10"), e_retr.get("found_at_10")
        if b_found != e_found:
            if e_found:
                improved = True
            else:
                regressed = True
        b_rank, e_rank = b_retr.get("best_rank"), e_retr.get("best_rank")
        if b_rank is not None and e_rank is not None and b_rank != e_rank:
            if e_rank < b_rank:
                improved = True
            else:
                regressed = True
        elif b_rank is None and e_rank is not None:
            improved = True
        elif b_rank is not None and e_rank is None:
            regressed = True

    if regressed:  # conservative: any regression signal regresses
        return "regressed"
    if improved:
        return "improved"
    return "unchanged"


def _delta(b: Optional[float], e: Optional[float]) -> Optional[float]:
    if b is None or e is None:
        return None
    return round(e - b, 4)


def compare_runs(baseline_results: list[dict],
                 experiment_results: list[dict]) -> dict:
    """Aggregate two runs' per-question results into a verdict report.

    Result dicts carry question_id, question_text, judge_scores, passed,
    retrieval_metrics, latency_ms. Metric deltas (experiment − baseline,
    None-safe) are computed over comparable questions only, so disjoint
    question subsets don't distort the aggregate.
    """
    b_map = {r["question_id"]: r for r in baseline_results}
    e_map = {r["question_id"]: r for r in experiment_results}
    ordered_ids = list(b_map) + [qid for qid in e_map if qid not in b_map]

    verdict_counts = {"improved": 0, "regressed": 0, "unchanged": 0}
    uncomparable = 0
    per_question = []
    comparable_b, comparable_e = [], []
    for qid in ordered_ids:
        b, e = b_map.get(qid), e_map.get(qid)
        verdict = classify_question_delta(b, e)
        if verdict == "uncomparable":
            uncomparable += 1
        else:
            verdict_counts[verdict] += 1
            comparable_b.append(b)
            comparable_e.append(e)
        per_question.append({
            "question_id": qid,
            "question_text": (b or e).get("question_text"),
            "verdict": verdict,
            "baseline": b,
            "experiment": e,
        })

    b_agg = aggregate_run_metrics(comparable_b)
    e_agg = aggregate_run_metrics(comparable_e)
    b_judge = b_agg.get("avg_judge_scores") or {}
    e_judge = e_agg.get("avg_judge_scores") or {}
    metric_deltas = {
        "found_at_5_rate": _delta(b_agg["found_at_5_rate"], e_agg["found_at_5_rate"]),
        "found_at_10_rate": _delta(b_agg["found_at_10_rate"], e_agg["found_at_10_rate"]),
        "mrr": _delta(b_agg["mrr"], e_agg["mrr"]),
        "avg_judge_scores": {k: _delta(b_judge.get(k), e_judge.get(k))
                             for k in JUDGE_KEYS},
        "latency_p50_ms": _delta(b_agg["latency_p50_ms"], e_agg["latency_p50_ms"]),
    }

    return {
        "verdict_counts": verdict_counts,
        "uncomparable": uncomparable,
        "per_question": per_question,
        "metric_deltas": metric_deltas,
    }


# -------------------- orchestration --------------------

async def start_comparison(db: AsyncSession, experiment_id: str,
                           question_set_id: str) -> dict:
    """Enqueue the baseline (agent) + experiment run pair for one question
    set. The single job worker executes them sequentially."""
    from app.services.evaluation.runner import EvalRunService

    exp = await db.get(Experiment, experiment_id)
    if not exp:
        raise ValueError(f"Experiment not found: {experiment_id}")
    if not exp.agent_id:
        raise ValueError("Experiment has no agent to baseline against")

    svc = EvalRunService(db)
    baseline = await svc.create_run("agent", exp.agent_id, question_set_id)
    experiment = await svc.create_run("experiment", exp.id, question_set_id)
    return {"baseline_run_id": baseline.id, "experiment_run_id": experiment.id}


async def load_comparison(db: AsyncSession, baseline_run_id: str,
                          experiment_run_id: str) -> dict:
    """Build the verdict JSON for two finished runs.

    Raises LookupError when either run is missing, ValueError when either
    has not finished (completed/partial)."""
    from app.services.evaluation.runner import EvalRunService

    svc = EvalRunService(db)
    sides = {}
    run_meta = {}
    for label, run_id in (("baseline", baseline_run_id),
                          ("experiment", experiment_run_id)):
        run = await svc.get_run(run_id)
        if not run:
            raise LookupError(f"Eval run not found: {run_id}")
        if run.status not in ("completed", "partial"):
            raise ValueError(f"Run has not finished: {run_id} (status: {run.status})")
        pairs = await svc.list_results(run_id)
        sides[label] = [
            {"question_id": q.id, "question_text": q.question_text,
             "judge_scores": res.judge_scores, "passed": res.passed,
             "retrieval_metrics": res.retrieval_metrics,
             "latency_ms": res.latency_ms}
            for res, q in pairs
        ]
        run_meta[f"{label}_run"] = {"run_id": run.id, "status": run.status,
                                    "target_type": run.target_type,
                                    "target_id": run.target_id,
                                    "target_label": run.target_label}
    return {**run_meta, **compare_runs(sides["baseline"], sides["experiment"])}
