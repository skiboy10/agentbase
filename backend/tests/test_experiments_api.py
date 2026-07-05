"""API tests for /api/experiments — library-scoped pipeline experiments
(create, compare, comparison verdict, promote)."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, EvalRun, Job, Library
from app.services.evaluation import QuestionSetService
from tests.factories import AgentFactory


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_api")
    db_session.add(lib)
    await db_session.commit()
    return lib


@pytest.fixture
async def agent(db_session: AsyncSession) -> Agent:
    a = AgentFactory.create(temperature=0.7, rag_top_k=5)
    db_session.add(a)
    await db_session.commit()
    return a


@pytest.fixture
async def question_set_id(db_session: AsyncSession, library: Library) -> str:
    qs = await QuestionSetService(db_session).create_set(
        library_id=library.id, name="Core")
    return qs.id


async def _create_experiment(client: AsyncClient, library, agent,
                             overrides=None) -> dict:
    resp = await client.post("/api/experiments", json={
        "library_id": library.id, "agent_id": agent.id,
        "name": "Low temp", "description": "ACME tuning",
        "overrides": overrides or {"temperature": 0.2, "rag_top_k": 8},
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestExperimentCrud:
    async def test_create_and_get(self, client, library, agent):
        exp = await _create_experiment(client, library, agent)
        assert exp["status"] == "ready"
        assert exp["experiment_type"] == "pipeline"
        assert exp["overrides"] == {"temperature": 0.2, "rag_top_k": 8}
        detail = await client.get(f"/api/experiments/{exp['id']}")
        assert detail.status_code == 200
        assert detail.json()["name"] == "Low temp"

    async def test_create_unknown_override_key_400(self, client, library, agent):
        resp = await client.post("/api/experiments", json={
            "library_id": library.id, "agent_id": agent.id,
            "name": "Bad", "overrides": {"chunk_size": 512},
        })
        assert resp.status_code == 400
        assert "chunk_size" in resp.json()["detail"]

    async def test_create_unknown_agent_404(self, client, library):
        resp = await client.post("/api/experiments", json={
            "library_id": library.id, "agent_id": "nope",
            "name": "x", "overrides": {"temperature": 0.2},
        })
        assert resp.status_code == 404

    async def test_list_filters_by_library(self, client, library, agent,
                                           db_session):
        await _create_experiment(client, library, agent)
        other = Library(name="Other", collection_name="kb_other_api")
        db_session.add(other)
        await db_session.commit()
        resp = await client.get(f"/api/experiments?library_id={library.id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        resp = await client.get(f"/api/experiments?library_id={other.id}")
        assert resp.json() == []

    async def test_delete(self, client, library, agent):
        exp = await _create_experiment(client, library, agent)
        resp = await client.delete(f"/api/experiments/{exp['id']}")
        assert resp.status_code == 204
        assert (await client.get(f"/api/experiments/{exp['id']}")).status_code == 404

    async def test_get_missing_404(self, client):
        assert (await client.get("/api/experiments/nope")).status_code == 404


class TestCompare:
    async def test_compare_creates_two_runs_and_jobs(self, client, library, agent,
                                                     question_set_id, db_session):
        exp = await _create_experiment(client, library, agent)
        resp = await client.post(f"/api/experiments/{exp['id']}/compare",
                                 json={"question_set_id": question_set_id})
        assert resp.status_code == 202, resp.text
        body = resp.json()
        runs = (await db_session.execute(select(EvalRun))).scalars().all()
        assert {r.id for r in runs} == {body["baseline_run_id"],
                                        body["experiment_run_id"]}
        jobs = (await db_session.execute(
            select(Job).where(Job.job_type == "run_scorecard"))).scalars().all()
        assert len(jobs) == 2

    async def test_compare_unknown_experiment_404(self, client, question_set_id):
        resp = await client.post("/api/experiments/nope/compare",
                                 json={"question_set_id": question_set_id})
        assert resp.status_code == 404

    async def test_comparison_unfinished_runs_409(self, client, library, agent,
                                                  question_set_id):
        exp = await _create_experiment(client, library, agent)
        body = (await client.post(f"/api/experiments/{exp['id']}/compare",
                                  json={"question_set_id": question_set_id})).json()
        resp = await client.get(
            f"/api/experiments/{exp['id']}/comparison"
            f"?baseline_run_id={body['baseline_run_id']}"
            f"&experiment_run_id={body['experiment_run_id']}")
        assert resp.status_code == 409

    async def test_comparison_missing_run_404(self, client, library, agent):
        exp = await _create_experiment(client, library, agent)
        resp = await client.get(
            f"/api/experiments/{exp['id']}/comparison"
            "?baseline_run_id=nope&experiment_run_id=nope2")
        assert resp.status_code == 404

    async def test_comparison_verdict_json(self, client, library, agent,
                                           question_set_id, db_session):
        exp = await _create_experiment(client, library, agent)
        body = (await client.post(f"/api/experiments/{exp['id']}/compare",
                                  json={"question_set_id": question_set_id})).json()
        # Finish both runs without executing (no results → empty comparison)
        for run_id in (body["baseline_run_id"], body["experiment_run_id"]):
            run = await db_session.get(EvalRun, run_id)
            run.status = "completed"
        await db_session.commit()
        resp = await client.get(
            f"/api/experiments/{exp['id']}/comparison"
            f"?baseline_run_id={body['baseline_run_id']}"
            f"&experiment_run_id={body['experiment_run_id']}")
        assert resp.status_code == 200
        out = resp.json()
        assert out["verdict_counts"] == {"improved": 0, "regressed": 0,
                                         "unchanged": 0}
        assert out["uncomparable"] == 0
        assert out["per_question"] == []
        assert "metric_deltas" in out
        assert out["baseline_run"]["run_id"] == body["baseline_run_id"]


class TestPromote:
    async def test_promote_mutates_agent_row(self, client, library, agent,
                                             db_session):
        exp = await _create_experiment(client, library, agent)
        resp = await client.post(f"/api/experiments/{exp['id']}/promote")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "promoted"
        assert resp.json()["promoted_at"] is not None
        row = await db_session.get(Agent, agent.id)
        assert row.temperature == 0.2
        assert row.rag_top_k == 8

    async def test_promote_twice_409(self, client, library, agent):
        exp = await _create_experiment(client, library, agent)
        assert (await client.post(
            f"/api/experiments/{exp['id']}/promote")).status_code == 200
        assert (await client.post(
            f"/api/experiments/{exp['id']}/promote")).status_code == 409

    async def test_promote_missing_404(self, client):
        assert (await client.post("/api/experiments/nope/promote")).status_code == 404
