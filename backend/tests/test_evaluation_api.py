"""Tests for /api/evaluation endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import EvalResult, EvalRun, Library


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_api")
    db_session.add(lib)
    await db_session.commit()
    return lib


class TestQuestionSetsAPI:
    async def test_create_and_list_sets(self, client: AsyncClient, library):
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Core"})
        assert r.status_code == 201
        set_id = r.json()["id"]

        r = await client.get(f"/api/evaluation/question-sets?library_id={library.id}")
        assert r.status_code == 200
        assert [s["id"] for s in r.json()] == [set_id]

    async def test_get_set_includes_questions(self, client: AsyncClient, library):
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Core"})
        set_id = r.json()["id"]
        r = await client.post(f"/api/evaluation/question-sets/{set_id}/questions",
                              json={"question_text": "What is ACME?",
                                    "expected_criteria": "Defines ACME"})
        assert r.status_code == 201
        r = await client.get(f"/api/evaluation/question-sets/{set_id}")
        body = r.json()
        assert len(body["questions"]) == 1
        assert body["questions"][0]["status"] == "active"

    async def test_update_question_status(self, client: AsyncClient, library):
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Core"})
        set_id = r.json()["id"]
        r = await client.post(f"/api/evaluation/question-sets/{set_id}/questions",
                              json={"question_text": "Q?"})
        qid = r.json()["id"]
        r = await client.patch(f"/api/evaluation/questions/{qid}",
                               json={"status": "archived"})
        assert r.status_code == 200
        assert r.json()["status"] == "archived"

    async def test_invalid_status_rejected(self, client: AsyncClient, library):
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Core"})
        set_id = r.json()["id"]
        r = await client.post(f"/api/evaluation/question-sets/{set_id}/questions",
                              json={"question_text": "Q?"})
        qid = r.json()["id"]
        r = await client.patch(f"/api/evaluation/questions/{qid}",
                               json={"status": "bogus"})
        assert r.status_code == 422

    async def test_generate_enqueues_job(self, client: AsyncClient, library,
                                          db_session: AsyncSession):
        from sqlalchemy import select
        from app.models import Job
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Core"})
        set_id = r.json()["id"]
        r = await client.post(f"/api/evaluation/question-sets/{set_id}/generate",
                              json={"questions_per_doc": 2, "doc_sample_size": 5})
        assert r.status_code == 202
        jobs = (await db_session.execute(
            select(Job).where(Job.job_type == "generate_questions"))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].payload["question_set_id"] == set_id

    async def test_generate_count_in_job_payload(self, client: AsyncClient, library,
                                                 db_session: AsyncSession):
        from sqlalchemy import select
        from app.models import Job
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Counted"})
        set_id = r.json()["id"]
        r = await client.post(f"/api/evaluation/question-sets/{set_id}/generate",
                              json={"count": 12})
        assert r.status_code == 202
        job = (await db_session.execute(
            select(Job).where(Job.job_type == "generate_questions"))).scalars().one()
        assert job.payload["count"] == 12

    async def test_generate_count_out_of_range_rejected(self, client: AsyncClient,
                                                        library):
        r = await client.post("/api/evaluation/question-sets",
                              json={"library_id": library.id, "name": "Bounds"})
        set_id = r.json()["id"]
        for bad in (4, 51, 0, -3):
            r = await client.post(
                f"/api/evaluation/question-sets/{set_id}/generate",
                json={"count": bad})
            assert r.status_code == 422, f"count={bad} should be rejected"

    async def test_missing_set_404(self, client: AsyncClient):
        r = await client.get("/api/evaluation/question-sets/nope")
        assert r.status_code == 404


@pytest.fixture
async def question_set_id(client: AsyncClient, library) -> str:
    r = await client.post("/api/evaluation/question-sets",
                          json={"library_id": library.id, "name": "Core"})
    return r.json()["id"]


async def _seed_run(db_session: AsyncSession, library, question_set_id: str,
                    question_text: str = "What is ACME?", *,
                    status: str = "completed",
                    judge_scores=None) -> tuple[EvalRun, EvalResult]:
    """Persist a finished run + one result directly (no job worker in tests)."""
    from app.services.evaluation import QuestionSetService
    q = await QuestionSetService(db_session).add_question(
        question_set_id, question_text, expected_criteria="Defines ACME")
    run = EvalRun(target_type="agent", target_id="agent-1", target_label="ACME Agent",
                  question_set_id=question_set_id, run_type="answer", status=status,
                  metrics_summary={"question_count": 1, "stale_questions": 0})
    db_session.add(run)
    await db_session.flush()
    result = EvalResult(eval_run_id=run.id, question_id=q.id,
                        retrieved=[{"document_id": "d1", "source_id": "s1",
                                    "title": "T", "score": 0.9}],
                        retrieval_metrics={"found_at_5": True, "found_at_10": True,
                                           "best_rank": 1, "reciprocal_rank": 1.0},
                        answer_text="ACME is a company.",
                        judge_scores=judge_scores, passed=bool(judge_scores) or None,
                        latency_ms=120)
    db_session.add(result)
    await db_session.commit()
    return run, result


class TestEvalRunsAPI:
    async def test_create_run_enqueues_job(self, client: AsyncClient, library,
                                           question_set_id, db_session: AsyncSession):
        from sqlalchemy import select
        from app.models import Job
        r = await client.post("/api/evaluation/runs",
                              json={"target_type": "library",
                                    "target_id": library.id,
                                    "question_set_id": question_set_id})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "pending"
        jobs = (await db_session.execute(
            select(Job).where(Job.job_type == "run_scorecard"))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].payload["run_id"] == body["run_id"]

    async def test_create_run_bad_target_404(self, client: AsyncClient,
                                             question_set_id):
        r = await client.post("/api/evaluation/runs",
                              json={"target_type": "library", "target_id": "nope",
                                    "question_set_id": question_set_id})
        assert r.status_code == 404

    async def test_create_run_invalid_target_type_rejected(self, client: AsyncClient,
                                                           question_set_id):
        # Literal["library", "agent"] → schema-level 422, same pattern as the
        # question status Literal.
        r = await client.post("/api/evaluation/runs",
                              json={"target_type": "bogus", "target_id": "x",
                                    "question_set_id": question_set_id})
        assert r.status_code == 422

    async def test_list_runs_filters_by_target(self, client: AsyncClient, library,
                                               question_set_id,
                                               db_session: AsyncSession):
        await _seed_run(db_session, library, question_set_id)
        r = await client.get("/api/evaluation/runs?target_type=agent&target_id=agent-1")
        assert r.status_code == 200
        runs = r.json()
        assert len(runs) == 1
        assert runs[0]["target_label"] == "ACME Agent"
        assert runs[0]["question_set_name"] == "Core"
        assert runs[0]["metrics_summary"]["question_count"] == 1
        assert "results" not in runs[0]  # summaries only

        r = await client.get("/api/evaluation/runs?target_id=other")
        assert r.json() == []

    async def test_run_detail_includes_results(self, client: AsyncClient, library,
                                               question_set_id,
                                               db_session: AsyncSession):
        run, _ = await _seed_run(db_session, library, question_set_id)
        r = await client.get(f"/api/evaluation/runs/{run.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == run.id
        assert len(body["results"]) == 1
        res = body["results"][0]
        assert res["question_text"] == "What is ACME?"
        assert res["origin"] == "manual"
        assert res["retrieval_metrics"]["best_rank"] == 1
        assert res["answer_text"] == "ACME is a company."

    async def test_run_detail_404(self, client: AsyncClient):
        r = await client.get("/api/evaluation/runs/nope")
        assert r.status_code == 404

    async def test_rejudge_fully_judged_409(self, client: AsyncClient, library,
                                            question_set_id,
                                            db_session: AsyncSession):
        run, _ = await _seed_run(
            db_session, library, question_set_id,
            judge_scores={"relevance": 1.0, "accuracy": 1.0, "groundedness": 1.0})
        r = await client.post(f"/api/evaluation/runs/{run.id}/rejudge")
        assert r.status_code == 409

    async def test_rejudge_running_409(self, client: AsyncClient, library,
                                       question_set_id, db_session: AsyncSession):
        run, _ = await _seed_run(db_session, library, question_set_id,
                                 status="running")
        r = await client.post(f"/api/evaluation/runs/{run.id}/rejudge")
        assert r.status_code == 409

    async def test_rejudge_enqueues_job(self, client: AsyncClient, library,
                                        question_set_id, db_session: AsyncSession):
        from sqlalchemy import select
        from app.models import Job
        run, _ = await _seed_run(db_session, library, question_set_id,
                                 status="partial", judge_scores=None)
        r = await client.post(f"/api/evaluation/runs/{run.id}/rejudge")
        assert r.status_code == 202
        jobs = (await db_session.execute(
            select(Job).where(Job.job_type == "run_scorecard"))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].payload == {"run_id": run.id, "rejudge": True}
