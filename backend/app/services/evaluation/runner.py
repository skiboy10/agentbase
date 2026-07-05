"""Scorecard run orchestration (design doc §3, §9).

Pure orchestration — retrieval math lives in metrics.py, answer grading in
judge.py. Retrieval runs call the production search path (RAGService with
default rerank); answer runs call the full agent pipeline (AgentQueryService)
then the LLM judge. Judge failures degrade the run to 'partial' and are
recoverable via rejudge()."""
import time
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.database import async_session_maker
from app.models import Document, EvalResult, EvalRun, Question, QuestionSet
from app.services.agent_query import AgentQueryService
from app.services.evaluation._targets import RETRIEVAL_TOP_K, resolve_target
from app.services.evaluation.judge import judge_answer
from app.services.evaluation.metrics import aggregate_run_metrics, score_retrieval
from app.services.job_service import JobService
from app.services.rag.service import RAGService

logger = structlog.get_logger()


def _retrieved_from_results(results, doc_lookup: Optional[dict] = None) -> list[dict]:
    """Ordered [{document_id, source_id, title, score}] from SearchResults.

    Question.expected_document_ids stores documents.id UUIDs, but a chunk's
    Qdrant payload carries the human-readable document KEY
    (documents.document_id, "srcprefix:hash") — so a payload id must be
    normalized through doc_lookup (path/url/document-key -> documents.id) or
    every retrieval comparison silently scores 0%. Chunks indexed before
    library-aware ingestion carry no document_id at all — those fall back to
    resolving the chunk's source path/url the same way."""
    doc_lookup = doc_lookup or {}
    out = []
    for r in results:
        doc_id = r.metadata.get("document_id")
        if doc_id:
            # Normalize document KEY -> documents.id UUID; leave unmapped
            # values as-is (already-UUID payloads from older experiments).
            doc_id = doc_lookup.get(doc_id, doc_id)
        else:
            for key in (r.source, getattr(r, "document_path", None),
                        r.metadata.get("source")):
                if key and key in doc_lookup:
                    doc_id = doc_lookup[key]
                    break
        out.append({
            "document_id": doc_id,
            "source_id": r.metadata.get("source_id"),
            "title": r.title or r.metadata.get("title") or "",
            # Reranker scores arrive as numpy float32 — not JSON serializable
            "score": float(r.score) if r.score is not None else None,
        })
    return out


class EvalRunService:
    """Create, execute, and re-judge scorecard runs (EvalRun/EvalResult)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------- creation --------------------

    async def create_run(self, target_type: str, target_id: str,
                         question_set_id: str) -> EvalRun:
        """Validate target + question set, snapshot config, enqueue the
        run_scorecard job, and return the pending EvalRun."""
        qs = await self.db.get(QuestionSet, question_set_id)
        if not qs:
            raise ValueError(f"Question set not found: {question_set_id}")

        run_type, target_label, config = await resolve_target(
            self.db, target_type, target_id)

        run = EvalRun(
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            question_set_id=question_set_id,
            run_type=run_type,
            config_snapshot=config,
            status="pending",
        )
        self.db.add(run)
        await self.db.flush()
        await JobService(self.db).enqueue(
            job_type="run_scorecard", payload={"run_id": run.id})
        await self.db.commit()
        await self.db.refresh(run)
        return run

    # -------------------- queries --------------------

    async def get_run(self, run_id: str) -> Optional[EvalRun]:
        return await self.db.get(EvalRun, run_id)

    async def list_runs(self, target_type: Optional[str] = None,
                        target_id: Optional[str] = None,
                        question_set_id: Optional[str] = None,
                        library_id: Optional[str] = None,
                        limit: int = 20) -> list[EvalRun]:
        stmt = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
        if target_type:
            stmt = stmt.where(EvalRun.target_type == target_type)
        if target_id:
            stmt = stmt.where(EvalRun.target_id == target_id)
        if question_set_id:
            stmt = stmt.where(EvalRun.question_set_id == question_set_id)
        if library_id:
            # Runs belong to a library via their question set (covers agent
            # runs too — sets are library-owned).
            stmt = stmt.join(QuestionSet,
                             EvalRun.question_set_id == QuestionSet.id
                             ).where(QuestionSet.library_id == library_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_results(self, run_id: str) -> list[tuple[EvalResult, Question]]:
        """Per-question results joined with their Question rows."""
        stmt = (select(EvalResult, Question)
                .join(Question, EvalResult.question_id == Question.id)
                .where(EvalResult.eval_run_id == run_id)
                .order_by(EvalResult.created_at.asc()))
        return list((await self.db.execute(stmt)).all())

    # -------------------- execution --------------------

    async def execute_run(self, run_id: str) -> EvalRun:
        """Run every active question against the target and persist grades."""
        run = await self.db.get(EvalRun, run_id)
        if not run:
            raise ValueError(f"Eval run not found: {run_id}")
        run.status = "running"
        run.started_at = datetime.utcnow()
        await self.db.commit()

        questions = (await self.db.execute(
            select(Question)
            .where(Question.question_set_id == run.question_set_id,
                   Question.status == "active")
            .order_by(Question.created_at.asc())
        )).scalars().all()
        runnable, n_stale = await self._exclude_stale(questions)

        if run.run_type == "retrieval":
            lookup_lib_ids = [run.target_id]
        else:
            lookup_lib_ids = (run.config_snapshot or {}).get("bound_library_ids") or []
        doc_lookup = await self._document_lookup(lookup_lib_ids)

        result_dicts: list[dict] = []
        for q in runnable:
            if run.run_type == "retrieval":
                rd = await self._score_retrieval_question(run, q, doc_lookup)
            else:
                rd = await self._score_answer_question(run, q, doc_lookup)
            self.db.add(EvalResult(eval_run_id=run.id, question_id=q.id, **rd))
            result_dicts.append(rd)

        summary = aggregate_run_metrics(result_dicts)
        summary["stale_questions"] = n_stale
        run.metrics_summary = summary
        unjudged = (run.run_type == "answer"
                    and any(rd["judge_scores"] is None for rd in result_dicts))
        run.status = "partial" if unjudged else "completed"
        run.finished_at = datetime.utcnow()
        await self.db.commit()
        await self._publish_completed(run)
        logger.info("Scorecard run finished", run_id=run.id, status=run.status,
                    questions=len(result_dicts), stale=n_stale)
        return run

    async def rejudge(self, run_id: str) -> EvalRun:
        """Re-judge results with no judge scores; may flip partial→completed."""
        run = await self.db.get(EvalRun, run_id)
        if not run:
            raise ValueError(f"Eval run not found: {run_id}")
        if run.run_type != "answer" or run.status not in ("partial", "completed"):
            raise ValueError(
                "Rejudge is only available for finished answer runs")

        pairs = await self.list_results(run_id)
        # Python-side null check: judge_scores is JSON — explicit None may be
        # stored as JSON null, which SQL "IS NULL" would not match.
        # Results with no answer_text had a failed agent query — judging an
        # empty answer would record an infra failure as a quality fail, so
        # they need a fresh run, not a rejudge.
        unjudged = [(res, q) for res, q in pairs
                    if res.judge_scores is None and res.answer_text is not None]
        if not unjudged:
            raise ValueError("Run has no unjudged results")

        for res, q in unjudged:
            judged = None
            try:
                judged = await judge_answer(
                    self.db, q.question_text, q.expected_criteria,
                    res.answer_text or "")
            except Exception as e:
                logger.warning("Rejudge: judge call failed", result_id=res.id,
                               error=str(e))
            if judged:
                res.judge_scores = judged["scores"]
                res.passed = judged["passed"]
                res.judge_rationale = judged["rationale"]

        all_results = [res for res, _ in pairs]
        summary = aggregate_run_metrics([
            {"retrieval_metrics": r.retrieval_metrics,
             "judge_scores": r.judge_scores,
             "passed": r.passed,
             "latency_ms": r.latency_ms}
            for r in all_results
        ])
        summary["stale_questions"] = (run.metrics_summary or {}).get(
            "stale_questions", 0)
        run.metrics_summary = summary
        if not any(r.judge_scores is None for r in all_results):
            run.status = "completed"
        await self.db.commit()
        await self._publish_completed(run)
        return run

    # -------------------- per-question scoring --------------------

    async def _exclude_stale(self, questions) -> tuple[list[Question], int]:
        """Questions whose expected docs were deleted are marked stale and
        excluded — they never score as 0% (design doc §9)."""
        expected_ids = {doc_id for q in questions
                        for doc_id in (q.expected_document_ids or [])}
        existing: set[str] = set()
        if expected_ids:
            existing = set((await self.db.execute(
                select(Document.id).where(Document.id.in_(expected_ids))
            )).scalars().all())
        runnable: list[Question] = []
        n_stale = 0
        for q in questions:
            expected = set(q.expected_document_ids or [])
            if expected and not expected.issubset(existing):
                q.status = "stale"
                n_stale += 1
                logger.info("Question marked stale (expected doc missing)",
                            question_id=q.id)
            else:
                runnable.append(q)
        if n_stale:
            await self.db.commit()
        return runnable, n_stale

    async def _document_lookup(self, library_ids: list[str]) -> dict[str, str]:
        """Map path/url/document-key -> documents.id for legacy chunks whose
        Qdrant payload predates library-aware ingestion (no document_id)."""
        if not library_ids:
            return {}
        rows = (await self.db.execute(
            select(Document.id, Document.document_id, Document.file_path,
                   Document.url)
            .where(Document.library_id.in_(library_ids))
        )).all()
        lookup: dict[str, str] = {}
        for doc_id, doc_key, file_path, url in rows:
            for k in (doc_key, file_path, url):
                if k:
                    lookup.setdefault(k, doc_id)
        return lookup

    async def _score_retrieval_question(self, run: EvalRun, q: Question,
                                        doc_lookup: Optional[dict] = None) -> dict:
        """Production search path, timed; grade against expected docs."""
        rag = RAGService(self.db)
        t0 = time.monotonic()
        results = await rag.search(
            query=q.question_text,
            knowledge_base_id=run.target_id,
            top_k=RETRIEVAL_TOP_K,
            rerank=True,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        retrieved = _retrieved_from_results(results, doc_lookup)
        return {
            "retrieved": retrieved,
            "retrieval_metrics": score_retrieval(
                [d["document_id"] for d in retrieved], q.expected_document_ids),
            "answer_text": None,
            "judge_scores": None,
            "judge_rationale": None,
            "passed": None,
            "latency_ms": latency_ms,
        }

    async def _score_answer_question(self, run: EvalRun, q: Question,
                                     doc_lookup: Optional[dict] = None) -> dict:
        """Full agent pipeline + LLM judge. Judge transport errors or
        unparseable output keep the result with judge_scores=None."""
        svc = AgentQueryService(self.db)
        snap = run.config_snapshot or {}
        if run.target_type == "experiment":
            # Experiment runs query the UNDERLYING agent with the experiment's
            # overrides applied for the duration of the query only.
            agent_id = snap.get("agent_id")
            overrides = snap.get("overrides") or None
        else:
            agent_id = run.target_id
            overrides = None
        t0 = time.monotonic()
        try:
            out = await svc.query(agent_id, q.question_text,
                                  include_raw_results=True,
                                  overrides=overrides)
        except Exception as e:
            # One failed agent query (LLM timeout, rate limit) must not abort
            # the whole run — keep the question unanswered/unjudged and let
            # the run finish 'partial' so the rest of the grades survive.
            logger.warning("Agent query failed — question kept unanswered",
                           question_id=q.id, error=str(e))
            return {
                "retrieved": None,
                "retrieval_metrics": None,
                "answer_text": None,
                "judge_scores": None,
                "judge_rationale": f"Agent query failed: {e}",
                "passed": None,
                "latency_ms": None,
            }
        latency_ms = int((time.monotonic() - t0) * 1000)
        retrieved = _retrieved_from_results(out.get("raw_results") or [],
                                            doc_lookup)
        answer_text = out.get("answer") or ""

        judged = None
        try:
            judged = await judge_answer(self.db, q.question_text,
                                        q.expected_criteria, answer_text)
        except Exception as e:
            logger.warning("Judge call failed — result kept unjudged",
                           question_id=q.id, error=str(e))
        return {
            "retrieved": retrieved,
            "retrieval_metrics": score_retrieval(
                [d["document_id"] for d in retrieved], q.expected_document_ids),
            "answer_text": answer_text,
            "judge_scores": judged["scores"] if judged else None,
            "judge_rationale": judged["rationale"] if judged else None,
            "passed": judged["passed"] if judged else None,
            "latency_ms": latency_ms,
        }

    # -------------------- events --------------------

    async def _publish_completed(self, run: EvalRun) -> None:
        from app.core.events import event_bus
        await event_bus.publish(
            event_type="evaluation.run_completed",
            payload={"run_id": run.id, "target_type": run.target_type,
                     "target_id": run.target_id, "status": run.status},
            source="system",
        )


async def run_scorecard_task(run_id: str, rejudge: bool = False) -> None:
    """Background task with its own session."""
    logger.info("Scorecard task started", run_id=run_id, rejudge=rejudge)
    async with async_session_maker() as db:
        service = EvalRunService(db)
        try:
            if rejudge:
                await service.rejudge(run_id)
            else:
                await service.execute_run(run_id)
        except Exception as e:
            logger.error("Scorecard task failed", run_id=run_id, error=str(e))
            try:
                await db.rollback()
                run = await db.get(EvalRun, run_id)
                if run and not rejudge:
                    run.status = "failed"
                    run.finished_at = datetime.utcnow()
                    await db.commit()
                    await service._publish_completed(run)
            except Exception as inner_e:
                logger.error("Failed to mark eval run failed", run_id=run_id,
                             error=str(inner_e))
            raise
