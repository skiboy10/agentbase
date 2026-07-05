"""Evaluation services: question sets, generation (Slice 1); scoring + judge
(Slice 2); pipeline experiments (Slice 3)."""
from app.services.evaluation.question_sets import QuestionSetService
from app.services.evaluation.judge import judge_answer
from app.services.evaluation.runner import EvalRunService, run_scorecard_task
from app.services.evaluation.experiments import (
    PIPELINE_OVERRIDABLE, ExperimentService,
)
from app.services.evaluation.compare import (
    JUDGE_DELTA_THRESHOLD, classify_question_delta, compare_runs,
    load_comparison, start_comparison,
)
from app.services.evaluation import metrics

__all__ = ["QuestionSetService", "judge_answer", "EvalRunService",
           "run_scorecard_task", "ExperimentService", "PIPELINE_OVERRIDABLE",
           "JUDGE_DELTA_THRESHOLD", "classify_question_delta", "compare_runs",
           "load_comparison", "start_comparison", "metrics"]
