"""MCP tools: evaluation question sets (Slice 1) + scorecard runs (Slice 2)
+ pipeline experiments, compare, promote (Slice 3)."""
from typing import Annotated, Optional
import structlog
from pydantic import Field

from app.core.auth import Scope, check_mcp_scope
from app.core.database import async_session_maker
from app.mcp.server import mcp
from app.services.evaluation import (
    EvalRunService, ExperimentService, QuestionSetService,
    load_comparison, start_comparison,
)
from app.services.job_service import JobService

logger = structlog.get_logger()


def _set_dict(qs) -> dict:
    return {"id": qs.id, "library_id": qs.library_id, "name": qs.name,
            "description": qs.description,
            "created_at": qs.created_at.isoformat() if qs.created_at else None}


def _question_dict(q) -> dict:
    return {"id": q.id, "question_set_id": q.question_set_id,
            "question_text": q.question_text,
            "expected_criteria": q.expected_criteria,
            "expected_document_ids": q.expected_document_ids,
            "tags": q.tags, "origin": q.origin, "status": q.status}


@mcp.tool(description="List evaluation question sets, optionally filtered by library_id.",
          annotations={"readOnlyHint": True})
async def agentbase_list_question_sets(library_id: Optional[str] = None) -> dict:
    async with async_session_maker() as db:
        sets = await QuestionSetService(db).list_sets(library_id=library_id)
        return {"question_sets": [_set_dict(s) for s in sets]}


@mcp.tool(description="Get a question set with all its questions.",
          annotations={"readOnlyHint": True})
async def agentbase_get_question_set(question_set_id: str) -> dict:
    async with async_session_maker() as db:
        svc = QuestionSetService(db)
        qs = await svc.get_set(question_set_id)
        if not qs:
            return {"error": f"Question set not found: {question_set_id}"}
        questions = await svc.list_questions(question_set_id)
        return {**_set_dict(qs), "questions": [_question_dict(q) for q in questions]}


@mcp.tool(description=("Create an evaluation question set for a library. Question sets "
                       "hold golden questions used to score retrieval and answer quality."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_create_question_set(library_id: str, name: str,
                              description: Optional[str] = None) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        qs = await QuestionSetService(db).create_set(
            library_id=library_id, name=name, description=description)
        return _set_dict(qs)


@mcp.tool(description=("Generate draft questions for a question set from the library's "
                       "own documents (background job). Drafts need curation: review with "
                       "agentbase_get_question_set, then agentbase_update_question status='active' to approve."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_generate_questions(
    question_set_id: str,
    questions_per_doc: Annotated[int, Field(ge=1, le=10)] = 3,
    doc_sample_size: Annotated[int, Field(ge=1, le=100)] = 10,
    count: Annotated[Optional[int], Field(
        ge=5, le=50,
        description="Total draft questions to generate (5-50, default 30). "
                    "When set, overrides doc_sample_size and caps the total.",
    )] = None,
) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        svc = QuestionSetService(db)
        if not await svc.get_set(question_set_id):
            return {"error": f"Question set not found: {question_set_id}"}
        job = await JobService(db).enqueue(
            job_type="generate_questions",
            payload={"question_set_id": question_set_id,
                     "questions_per_doc": questions_per_doc,
                     "doc_sample_size": doc_sample_size,
                     "count": count})
        await db.commit()
        return {"job_id": job.id, "status": "queued",
                "next": "Poll agentbase_get_question_set for new draft questions."}


@mcp.tool(description="Add a question to a question set (created active — manual questions are trusted).",
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_add_question(question_set_id: str, question_text: str,
                       expected_criteria: Optional[str] = None,
                       expected_document_ids: Optional[list[str]] = None,
                       tags: Optional[list[str]] = None) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        svc = QuestionSetService(db)
        if not await svc.get_set(question_set_id):
            return {"error": f"Question set not found: {question_set_id}"}
        q = await svc.add_question(
            question_set_id=question_set_id, question_text=question_text,
            expected_criteria=expected_criteria,
            expected_document_ids=expected_document_ids, tags=tags, origin="manual")
        return _question_dict(q)


@mcp.tool(description=("Update a question. Set status='active' to approve a draft, "
                       "'archived' to retire. Statuses: draft|active|archived|stale."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_update_question(question_id: str, question_text: Optional[str] = None,
                          expected_criteria: Optional[str] = None,
                          expected_document_ids: Optional[list[str]] = None,
                          tags: Optional[list[str]] = None,
                          status: Optional[str] = None) -> dict:
    check_mcp_scope(Scope.WRITE)
    # Only pass fields the caller actually provided — the service treats a
    # present key as "set this value", so passing None for omitted params
    # would clear them. (MCP therefore can't clear a field to null; use the
    # REST API for that.)
    fields = {k: v for k, v in {
        "question_text": question_text,
        "expected_criteria": expected_criteria,
        "expected_document_ids": expected_document_ids,
        "tags": tags,
        "status": status,
    }.items() if v is not None}
    async with async_session_maker() as db:
        try:
            q = await QuestionSetService(db).update_question(question_id, **fields)
        except ValueError as e:
            return {"error": str(e)}
        if not q:
            return {"error": f"Question not found: {question_id}"}
        return _question_dict(q)


@mcp.tool(description=("Delete a question. Questions that already have eval results are "
                       "archived instead of deleted (history preservation)."),
          annotations={"readOnlyHint": False, "destructiveHint": True})
async def agentbase_delete_question(question_id: str) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        outcome = await QuestionSetService(db).delete_question(question_id)
        if outcome is None:
            return {"error": f"Question not found: {question_id}"}
        return {"outcome": outcome}


# ============================================================
# Scorecard runs (Slice 2)
# ============================================================

def _run_dict(run) -> dict:
    return {"run_id": run.id, "target_type": run.target_type,
            "target_id": run.target_id, "target_label": run.target_label,
            "question_set_id": run.question_set_id, "run_type": run.run_type,
            "status": run.status, "metrics_summary": run.metrics_summary,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None}


@mcp.tool(description=("Run a scorecard: score a question set against a target. "
                       "target_type 'library' grades retrieval (found@k, MRR); "
                       "'agent' grades full answers with an LLM judge. Runs in the "
                       "background — poll agentbase_get_eval_run for the report."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_run_scorecard(target_type: str, target_id: str,
                        question_set_id: str) -> dict:
    check_mcp_scope(Scope.WRITE)
    if target_type not in ("library", "agent"):
        return {"error": f"Invalid target_type: {target_type} (library | agent)"}
    async with async_session_maker() as db:
        try:
            run = await EvalRunService(db).create_run(
                target_type, target_id, question_set_id)
        except ValueError as e:
            return {"error": str(e)}
        return {"run_id": run.id, "status": run.status,
                "next": "Poll agentbase_get_eval_run with this run_id until status is "
                        "completed or partial."}


@mcp.tool(description=("Get a scorecard run: status + aggregate metrics. Pass "
                       "include_results=True for per-question grades (question_text, "
                       "retrieval_metrics, judge_scores, passed, rationale)."),
          annotations={"readOnlyHint": True})
async def agentbase_get_eval_run(run_id: str, include_results: bool = False) -> dict:
    async with async_session_maker() as db:
        svc = EvalRunService(db)
        run = await svc.get_run(run_id)
        if not run:
            return {"error": f"Eval run not found: {run_id}"}
        out = _run_dict(run)
        if include_results:
            pairs = await svc.list_results(run_id)
            out["results"] = [
                {"question_id": q.id, "question_text": q.question_text,
                 "expected_criteria": q.expected_criteria,
                 "retrieval_metrics": res.retrieval_metrics,
                 "judge_scores": res.judge_scores, "passed": res.passed,
                 "rationale": res.judge_rationale,
                 "latency_ms": res.latency_ms}
                for res, q in pairs
            ]
        return out


@mcp.tool(description=("List scorecard runs, newest first. Filter by target_type "
                       "(library | agent), target_id, or question_set_id."),
          annotations={"readOnlyHint": True})
async def agentbase_list_eval_runs(target_type: Optional[str] = None,
                         target_id: Optional[str] = None,
                         question_set_id: Optional[str] = None,
                         limit: int = 10) -> dict:
    async with async_session_maker() as db:
        runs = await EvalRunService(db).list_runs(
            target_type=target_type, target_id=target_id,
            question_set_id=question_set_id, limit=limit)
        return {"runs": [_run_dict(r) for r in runs]}


@mcp.tool(description=("Re-judge a partial answer run's unjudged results (e.g. after "
                       "a judge-LLM outage). Errors if the run is still in progress "
                       "or has no unjudged results."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_rejudge_eval_run(run_id: str) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        svc = EvalRunService(db)
        run = await svc.get_run(run_id)
        if not run:
            return {"error": f"Eval run not found: {run_id}"}
        if run.status in ("pending", "running"):
            return {"error": "Run is still in progress"}
        if run.run_type != "answer":
            return {"error": "Rejudge only applies to answer runs"}
        pairs = await svc.list_results(run_id)
        if not any(res.judge_scores is None for res, _ in pairs):
            return {"error": "Run has no unjudged results"}
        job = await JobService(db).enqueue(
            job_type="run_scorecard", payload={"run_id": run_id, "rejudge": True})
        await db.commit()
        return {"job_id": job.id, "run_id": run_id, "status": "queued",
                "next": "Poll agentbase_get_eval_run until status flips to completed."}


# ============================================================
# Pipeline experiments + compare + promote (Slice 3)
# ============================================================

def _experiment_dict(exp) -> dict:
    return {"id": exp.id, "library_id": exp.library_id, "agent_id": exp.agent_id,
            "name": exp.name, "description": exp.description,
            "experiment_type": exp.experiment_type, "overrides": exp.overrides,
            "status": exp.status, "error_message": exp.error_message,
            "created_at": exp.created_at.isoformat() if exp.created_at else None,
            "promoted_at": exp.promoted_at.isoformat() if exp.promoted_at else None}


@mcp.tool(description=("Create a pipeline experiment: an agent-anchored set of "
                       "query-time config overrides scored against question sets "
                       "without reindexing. Override keys (Agent column names "
                       "verbatim): system_prompt, model_provider, model_name, "
                       "temperature, rag_top_k. Example overrides: "
                       '{"temperature": 0.2, "rag_top_k": 8}.'),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_create_experiment(library_id: str, agent_id: str, name: str,
                            overrides: dict,
                            description: Optional[str] = None) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        try:
            exp = await ExperimentService(db).create_experiment(
                library_id=library_id, name=name, agent_id=agent_id,
                overrides=overrides, description=description)
        except ValueError as e:
            return {"error": str(e)}
        return {**_experiment_dict(exp),
                "next": "Call agentbase_compare_experiment with a question_set_id to "
                        "score it against the agent's baseline."}


@mcp.tool(description="List pipeline experiments, optionally filtered by library_id or agent_id.",
          annotations={"readOnlyHint": True})
async def agentbase_list_experiments(library_id: Optional[str] = None,
                           agent_id: Optional[str] = None) -> dict:
    async with async_session_maker() as db:
        exps = await ExperimentService(db).list_experiments(
            library_id=library_id, agent_id=agent_id)
        return {"experiments": [_experiment_dict(e) for e in exps]}


@mcp.tool(description="Get an experiment: overrides, status (ready | promoted), timestamps.",
          annotations={"readOnlyHint": True})
async def agentbase_get_experiment(experiment_id: str) -> dict:
    async with async_session_maker() as db:
        exp = await ExperimentService(db).get_experiment(experiment_id)
        if not exp:
            return {"error": f"Experiment not found: {experiment_id}"}
        return _experiment_dict(exp)


@mcp.tool(description=("Compare an experiment against its agent's baseline on a "
                       "question set. Enqueues TWO scorecard runs (baseline agent + "
                       "experiment) executed sequentially in the background."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_compare_experiment(experiment_id: str, question_set_id: str) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        try:
            out = await start_comparison(db, experiment_id, question_set_id)
        except ValueError as e:
            return {"error": str(e)}
        return {**out,
                "next": "Poll agentbase_get_eval_run on both run ids until completed or "
                        "partial; then call agentbase_get_comparison with both ids."}


@mcp.tool(description=("Verdict report for a finished compare pair: per-question "
                       "improved | regressed | unchanged | uncomparable, verdict "
                       "counts, and metric deltas (experiment - baseline)."),
          annotations={"readOnlyHint": True})
async def agentbase_get_comparison(baseline_run_id: str, experiment_run_id: str) -> dict:
    async with async_session_maker() as db:
        try:
            return await load_comparison(db, baseline_run_id, experiment_run_id)
        except (LookupError, ValueError) as e:
            return {"error": str(e)}


@mcp.tool(description=("Promote a ready experiment: write its overrides into the "
                       "agent's LIVE config (system_prompt, model, temperature, "
                       "rag_top_k as overridden). Irreversible from here — the "
                       "previous values are not stored."),
          annotations={"readOnlyHint": False, "destructiveHint": False})
async def agentbase_promote_experiment(experiment_id: str) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        try:
            exp = await ExperimentService(db).promote(experiment_id)
        except ValueError as e:
            return {"error": str(e)}
        return _experiment_dict(exp)


@mcp.tool(description=("Delete an experiment (promoted ones included — scorecard "
                       "history lives in eval runs, not the experiment row)."),
          annotations={"readOnlyHint": False, "destructiveHint": True})
async def agentbase_delete_experiment(experiment_id: str) -> dict:
    check_mcp_scope(Scope.WRITE)
    async with async_session_maker() as db:
        if not await ExperimentService(db).delete_experiment(experiment_id):
            return {"error": f"Experiment not found: {experiment_id}"}
        return {"deleted": experiment_id}
