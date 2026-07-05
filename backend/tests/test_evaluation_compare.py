"""Tests for the comparison verdict engine (design doc §4).

classify_question_delta is pure: it sees one question's baseline/experiment
result dicts and returns improved|regressed|unchanged|uncomparable.
Conservative rule: any regression signal regresses, even when other signals
improved ("mixed" counts as regressed in the aggregate).
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalRun, Job, Library
from app.services.evaluation.compare import (
    JUDGE_DELTA_THRESHOLD, classify_question_delta, compare_runs,
    start_comparison,
)
from app.services.evaluation.experiments import ExperimentService
from app.services.evaluation.question_sets import QuestionSetService
from tests.factories import AgentFactory


def _result(question_id="q1", question_text="What is ACME?",
            judge=None, passed=None, retrieval=None, latency_ms=100):
    return {"question_id": question_id, "question_text": question_text,
            "judge_scores": judge, "passed": passed,
            "retrieval_metrics": retrieval, "latency_ms": latency_ms}


def _judge(mean: float) -> dict:
    return {"relevance": mean, "accuracy": mean, "groundedness": mean}


def _retr(found_10=True, best_rank=1):
    return {"found_at_5": best_rank is not None and best_rank <= 5,
            "found_at_10": found_10, "best_rank": best_rank,
            "reciprocal_rank": (1.0 / best_rank) if best_rank else 0.0}


class TestClassifyQuestionDelta:
    def test_threshold_constant(self):
        assert JUDGE_DELTA_THRESHOLD == 0.1

    def test_judge_mean_up_improved(self):
        assert classify_question_delta(
            _result(judge=_judge(0.7), passed=True),
            _result(judge=_judge(0.85), passed=True)) == "improved"

    def test_judge_mean_down_regressed(self):
        assert classify_question_delta(
            _result(judge=_judge(0.85), passed=True),
            _result(judge=_judge(0.7), passed=True)) == "regressed"

    def test_small_judge_delta_unchanged(self):
        assert classify_question_delta(
            _result(judge=_judge(0.80), passed=True),
            _result(judge=_judge(0.85), passed=True)) == "unchanged"
        assert classify_question_delta(
            _result(judge=_judge(0.85), passed=True),
            _result(judge=_judge(0.80), passed=True)) == "unchanged"

    def test_passed_flip_overrides_small_judge_delta(self):
        assert classify_question_delta(
            _result(judge=_judge(0.80), passed=False),
            _result(judge=_judge(0.84), passed=True)) == "improved"
        assert classify_question_delta(
            _result(judge=_judge(0.84), passed=True),
            _result(judge=_judge(0.80), passed=False)) == "regressed"

    def test_found_at_10_flip(self):
        assert classify_question_delta(
            _result(retrieval=_retr(found_10=False, best_rank=None)),
            _result(retrieval=_retr(found_10=True, best_rank=4))) == "improved"
        assert classify_question_delta(
            _result(retrieval=_retr(found_10=True, best_rank=4)),
            _result(retrieval=_retr(found_10=False, best_rank=None))) == "regressed"

    def test_best_rank_change(self):
        assert classify_question_delta(
            _result(retrieval=_retr(best_rank=7)),
            _result(retrieval=_retr(best_rank=2))) == "improved"
        assert classify_question_delta(
            _result(retrieval=_retr(best_rank=2)),
            _result(retrieval=_retr(best_rank=7))) == "regressed"

    def test_mixed_counts_as_regressed(self):
        # Retrieval improved (rank 7→2) but judge regressed −0.2:
        # conservative — any regression signal regresses.
        assert classify_question_delta(
            _result(judge=_judge(0.9), passed=True, retrieval=_retr(best_rank=7)),
            _result(judge=_judge(0.7), passed=True, retrieval=_retr(best_rank=2)),
        ) == "regressed"

    def test_missing_side_uncomparable(self):
        assert classify_question_delta(None, _result()) == "uncomparable"
        assert classify_question_delta(_result(), None) == "uncomparable"

    def test_no_signals_unchanged(self):
        assert classify_question_delta(_result(), _result()) == "unchanged"


class TestCompareRuns:
    def test_compare_runs_shape_and_counts(self):
        baseline = [
            _result("q1", "Q one?", judge=_judge(0.6), passed=False,
                    retrieval=_retr(best_rank=5), latency_ms=100),
            _result("q2", "Q two?", judge=_judge(0.9), passed=True,
                    retrieval=_retr(best_rank=1), latency_ms=100),
            _result("q3", "Q three?", judge=_judge(0.8), passed=True,
                    retrieval=_retr(best_rank=2), latency_ms=100),
            _result("q4", "Q four (baseline only)?", judge=_judge(0.5)),
        ]
        experiment = [
            _result("q1", "Q one?", judge=_judge(0.9), passed=True,
                    retrieval=_retr(best_rank=1), latency_ms=80),     # improved
            _result("q2", "Q two?", judge=_judge(0.6), passed=False,
                    retrieval=_retr(best_rank=1), latency_ms=80),     # regressed
            _result("q3", "Q three?", judge=_judge(0.82), passed=True,
                    retrieval=_retr(best_rank=2), latency_ms=80),     # unchanged
            _result("q5", "Q five (experiment only)?", judge=_judge(0.5)),
        ]
        out = compare_runs(baseline, experiment)
        assert out["verdict_counts"] == {"improved": 1, "regressed": 1,
                                         "unchanged": 1}
        assert out["uncomparable"] == 2
        per_q = {p["question_id"]: p for p in out["per_question"]}
        assert per_q["q1"]["verdict"] == "improved"
        assert per_q["q2"]["verdict"] == "regressed"
        assert per_q["q3"]["verdict"] == "unchanged"
        assert per_q["q4"]["verdict"] == "uncomparable"
        assert per_q["q5"]["verdict"] == "uncomparable"
        assert per_q["q1"]["question_text"] == "Q one?"
        assert per_q["q1"]["baseline"]["judge_scores"]["accuracy"] == 0.6
        assert per_q["q1"]["experiment"]["judge_scores"]["accuracy"] == 0.9
        # Deltas = experiment − baseline (comparable questions aggregated)
        deltas = out["metric_deltas"]
        assert deltas["latency_p50_ms"] == -20.0
        assert "found_at_5_rate" in deltas
        assert "found_at_10_rate" in deltas
        assert "mrr" in deltas
        assert deltas["avg_judge_scores"]["relevance"] is not None

    def test_compare_runs_none_safe_deltas(self):
        # Retrieval-free answer runs: no retrieval metrics, no latency on one side
        baseline = [_result("q1", judge=_judge(0.5), latency_ms=None)]
        experiment = [_result("q1", judge=_judge(0.9), latency_ms=None)]
        out = compare_runs(baseline, experiment)
        deltas = out["metric_deltas"]
        assert deltas["found_at_5_rate"] is None
        assert deltas["mrr"] is None
        assert deltas["latency_p50_ms"] is None
        assert deltas["avg_judge_scores"]["accuracy"] == pytest.approx(0.4)


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_cmp")
    db_session.add(lib)
    await db_session.commit()
    return lib


class TestStartComparison:
    async def test_start_comparison_creates_two_runs(self, db_session, library):
        agent = AgentFactory.create()
        db_session.add(agent)
        await db_session.commit()
        exp = await ExperimentService(db_session).create_experiment(
            library_id=library.id, name="Tuned", agent_id=agent.id,
            overrides={"temperature": 0.2})
        qs = await QuestionSetService(db_session).create_set(
            library_id=library.id, name="Core")

        out = await start_comparison(db_session, exp.id, qs.id)

        baseline = await db_session.get(EvalRun, out["baseline_run_id"])
        experiment = await db_session.get(EvalRun, out["experiment_run_id"])
        assert baseline.target_type == "agent"
        assert baseline.target_id == agent.id
        assert experiment.target_type == "experiment"
        assert experiment.target_id == exp.id
        assert baseline.question_set_id == qs.id
        assert experiment.question_set_id == qs.id
        # Two scorecard jobs queued (executed sequentially by the worker)
        jobs = (await db_session.execute(
            __import__("sqlalchemy").select(Job)
            .where(Job.job_type == "run_scorecard"))).scalars().all()
        assert {j.payload["run_id"] for j in jobs} == {baseline.id, experiment.id}

    async def test_start_comparison_unknown_experiment(self, db_session, library):
        qs = await QuestionSetService(db_session).create_set(
            library_id=library.id, name="Core")
        with pytest.raises(ValueError):
            await start_comparison(db_session, "nope", qs.id)
