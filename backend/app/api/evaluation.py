"""Evaluation API: question sets + curation (Slice 1), scorecard runs (Slice 2)."""
from typing import Optional, Literal
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey, QuestionSet
from app.services.evaluation import EvalRunService, QuestionSetService
from app.services.evaluation.generation import (
    GENERATION_COUNT_MAX, GENERATION_COUNT_MIN,
)
from app.services.job_service import JobService

router = APIRouter()


class QuestionSetCreate(BaseModel):
    library_id: str
    name: str
    description: Optional[str] = None


class QuestionSetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class QuestionCreate(BaseModel):
    question_text: str
    expected_criteria: Optional[str] = None
    expected_document_ids: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    expected_criteria: Optional[str] = None
    expected_document_ids: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    status: Optional[Literal["draft", "active", "archived", "stale"]] = None


class GenerateRequest(BaseModel):
    questions_per_doc: int = Field(3, ge=1, le=10)
    doc_sample_size: int = Field(10, ge=1, le=100)
    # Total draft target (issue #194). When set, overrides doc_sample_size
    # (enough docs are sampled to reach it) and caps the total created.
    count: Optional[int] = Field(
        None, ge=GENERATION_COUNT_MIN, le=GENERATION_COUNT_MAX,
        description="Total draft questions to generate (5-50, default 30).")


class QuestionResponse(BaseModel):
    id: str
    question_set_id: str
    question_text: str
    expected_criteria: Optional[str]
    expected_document_ids: Optional[list]
    tags: Optional[list]
    origin: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionSetResponse(BaseModel):
    id: str
    library_id: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    question_counts: dict[str, int] = {}  # status -> count

    class Config:
        from_attributes = True


class QuestionSetDetailResponse(QuestionSetResponse):
    questions: list[QuestionResponse] = []


@router.get("/question-sets", response_model=list[QuestionSetResponse])
async def list_question_sets(library_id: Optional[str] = Query(None),
                             db: AsyncSession = Depends(get_db),
                             _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    svc = QuestionSetService(db)
    sets = await svc.list_sets(library_id=library_id)
    counts = await svc.question_counts([s.id for s in sets])
    out = []
    for s in sets:
        resp = QuestionSetResponse.model_validate(s)
        resp.question_counts = counts.get(s.id, {})
        out.append(resp)
    return out


@router.post("/question-sets", response_model=QuestionSetResponse, status_code=201)
async def create_question_set(body: QuestionSetCreate, db: AsyncSession = Depends(get_db),
                              _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    return await QuestionSetService(db).create_set(
        library_id=body.library_id, name=body.name, description=body.description)


@router.get("/question-sets/{set_id}", response_model=QuestionSetDetailResponse)
async def get_question_set(set_id: str, db: AsyncSession = Depends(get_db),
                           _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    svc = QuestionSetService(db)
    qs = await svc.get_set(set_id)
    if not qs:
        raise HTTPException(status_code=404, detail="Question set not found")
    questions = await svc.list_questions(set_id)
    # Validate via the base model first: model_validate on the detail model would
    # touch qs.questions (an unloaded async relationship) and raise MissingGreenlet.
    return QuestionSetDetailResponse(
        **QuestionSetResponse.model_validate(qs).model_dump(),
        questions=[QuestionResponse.model_validate(q) for q in questions],
    )


@router.patch("/question-sets/{set_id}", response_model=QuestionSetResponse)
async def update_question_set(set_id: str, body: QuestionSetUpdate,
                              db: AsyncSession = Depends(get_db),
                              _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    qs = await QuestionSetService(db).update_set(set_id, **body.model_dump(exclude_unset=True))
    if not qs:
        raise HTTPException(status_code=404, detail="Question set not found")
    return qs


@router.delete("/question-sets/{set_id}", status_code=204)
async def delete_question_set(set_id: str, db: AsyncSession = Depends(get_db),
                              _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    if not await QuestionSetService(db).delete_set(set_id):
        raise HTTPException(status_code=404, detail="Question set not found")


@router.post("/question-sets/{set_id}/questions", response_model=QuestionResponse,
             status_code=201)
async def add_question(set_id: str, body: QuestionCreate,
                       db: AsyncSession = Depends(get_db),
                       _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    svc = QuestionSetService(db)
    if not await svc.get_set(set_id):
        raise HTTPException(status_code=404, detail="Question set not found")
    return await svc.add_question(
        question_set_id=set_id, question_text=body.question_text,
        expected_criteria=body.expected_criteria,
        expected_document_ids=body.expected_document_ids,
        tags=body.tags, origin="manual")


@router.patch("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(question_id: str, body: QuestionUpdate,
                          db: AsyncSession = Depends(get_db),
                          _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    try:
        q = await QuestionSetService(db).update_question(
            question_id, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return q


@router.delete("/questions/{question_id}")
async def delete_question(question_id: str, db: AsyncSession = Depends(get_db),
                          _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    outcome = await QuestionSetService(db).delete_question(question_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"outcome": outcome}  # "deleted" | "archived"


@router.post("/question-sets/{set_id}/generate", status_code=202)
async def generate_questions(set_id: str, body: GenerateRequest,
                             db: AsyncSession = Depends(get_db),
                             _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    svc = QuestionSetService(db)
    if not await svc.get_set(set_id):
        raise HTTPException(status_code=404, detail="Question set not found")
    job = await JobService(db).enqueue(
        job_type="generate_questions",
        payload={"question_set_id": set_id,
                 "questions_per_doc": body.questions_per_doc,
                 "doc_sample_size": body.doc_sample_size,
                 "count": body.count})
    await db.commit()
    return {"job_id": job.id, "status": "queued"}


# ============================================================
# Scorecard runs (Slice 2)
# ============================================================

class EvalRunCreate(BaseModel):
    target_type: Literal["library", "agent"]
    target_id: str
    question_set_id: str


class EvalRunSummary(BaseModel):
    id: str
    target_type: str
    target_id: str
    target_label: str
    question_set_id: str
    question_set_name: str = ""
    run_type: str
    status: str
    metrics_summary: Optional[dict]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class EvalResultResponse(BaseModel):
    id: str
    question_id: str
    question_text: str
    expected_criteria: Optional[str]
    expected_document_ids: Optional[list] = None
    origin: str
    tags: Optional[list]
    retrieved: Optional[list]
    retrieval_metrics: Optional[dict]
    answer_text: Optional[str]
    judge_scores: Optional[dict]
    judge_rationale: Optional[str]
    passed: Optional[bool]
    latency_ms: Optional[int]


class EvalRunDetail(EvalRunSummary):
    results: list[EvalResultResponse] = []


async def _set_names(db: AsyncSession, set_ids: list[str]) -> dict[str, str]:
    if not set_ids:
        return {}
    rows = (await db.execute(
        select(QuestionSet.id, QuestionSet.name)
        .where(QuestionSet.id.in_(set_ids)))).all()
    return {sid: name for sid, name in rows}


@router.get("/runs", response_model=list[EvalRunSummary])
async def list_eval_runs(target_type: Optional[str] = Query(None),
                         target_id: Optional[str] = Query(None),
                         question_set_id: Optional[str] = Query(None),
                         library_id: Optional[str] = Query(None),
                         limit: int = Query(20, ge=1, le=100),
                         db: AsyncSession = Depends(get_db),
                         _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    runs = await EvalRunService(db).list_runs(
        target_type=target_type, target_id=target_id,
        question_set_id=question_set_id, library_id=library_id, limit=limit)
    names = await _set_names(db, [r.question_set_id for r in runs])
    out = []
    for r in runs:
        resp = EvalRunSummary.model_validate(r)
        resp.question_set_name = names.get(r.question_set_id, "")
        out.append(resp)
    return out


@router.post("/runs", status_code=202)
async def create_eval_run(body: EvalRunCreate, db: AsyncSession = Depends(get_db),
                          _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    try:
        # create_run validates target + set, snapshots config, and enqueues
        # the run_scorecard job.
        run = await EvalRunService(db).create_run(
            body.target_type, body.target_id, body.question_set_id)
    except ValueError as e:
        status = 400 if "Invalid target_type" in str(e) else 404
        raise HTTPException(status_code=status, detail=str(e))
    return {"run_id": run.id, "status": "pending"}


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
async def get_eval_run(run_id: str, db: AsyncSession = Depends(get_db),
                       _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    svc = EvalRunService(db)
    run = await svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    names = await _set_names(db, [run.question_set_id])
    pairs = await svc.list_results(run_id)
    detail = EvalRunDetail(
        **EvalRunSummary.model_validate(run).model_dump(),
        results=[
            EvalResultResponse(
                id=res.id, question_id=res.question_id,
                question_text=q.question_text,
                expected_criteria=q.expected_criteria,
                expected_document_ids=q.expected_document_ids,
                origin=q.origin, tags=q.tags,
                retrieved=res.retrieved,
                retrieval_metrics=res.retrieval_metrics,
                answer_text=res.answer_text,
                judge_scores=res.judge_scores,
                judge_rationale=res.judge_rationale,
                passed=res.passed,
                latency_ms=res.latency_ms,
            )
            for res, q in pairs
        ],
    )
    detail.question_set_name = names.get(run.question_set_id, "")
    return detail


@router.post("/runs/{run_id}/rejudge", status_code=202)
async def rejudge_eval_run(run_id: str, db: AsyncSession = Depends(get_db),
                           _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    svc = EvalRunService(db)
    run = await svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    if run.status in ("pending", "running"):
        raise HTTPException(status_code=409, detail="Run is still in progress")
    if run.run_type != "answer":
        raise HTTPException(status_code=409,
                            detail="Rejudge only applies to answer runs")
    # judge_scores is JSON — filter Python-side (explicit None may persist as
    # JSON null, which SQL IS NULL would miss).
    pairs = await svc.list_results(run_id)
    if not any(res.judge_scores is None for res, _ in pairs):
        raise HTTPException(status_code=409, detail="Run has no unjudged results")
    job = await JobService(db).enqueue(
        job_type="run_scorecard", payload={"run_id": run_id, "rejudge": True})
    await db.commit()
    return {"job_id": job.id, "run_id": run_id, "status": "queued"}
