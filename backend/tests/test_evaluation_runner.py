"""Tests for EvalRunService — scorecard execution, stale detection, rejudge.

RAGService and AgentQueryService are patched at their import site in runner.py;
judge_answer likewise (app.services.evaluation.runner.judge_answer)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, EvalResult, EvalRun, Job, Library
from app.services.evaluation import QuestionSetService
from app.services.evaluation.runner import EvalRunService
from app.services.rag.types import SearchResult
from tests.factories import AgentFactory


def _hit(document_id: str, score: float = 0.9, source_id: str = "s1") -> SearchResult:
    return SearchResult(
        content="chunk text",
        source="https://example.com/doc",
        score=score,
        title="ACME Guide",
        metadata={"document_id": document_id, "source_id": source_id,
                  "title": "ACME Guide", "source_name": "ACME Source"},
    )


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_runs",
                  embedding_provider="ollama", embedding_model="qwen3-embedding:4b")
    db_session.add(lib)
    await db_session.commit()
    return lib


@pytest.fixture
async def docs(db_session: AsyncSession, library: Library) -> list[Document]:
    out = []
    for i in range(2):
        d = Document(library_id=library.id, document_id=f"/tmp/acme/doc{i}.md",
                     title=f"ACME Guide {i}", full_text=f"Guide {i} content.")
        db_session.add(d)
        out.append(d)
    await db_session.commit()
    return out


@pytest.fixture
async def question_set(db_session: AsyncSession, library: Library):
    return await QuestionSetService(db_session).create_set(
        library_id=library.id, name="Core")


@pytest.fixture
async def agent(db_session: AsyncSession):
    a = AgentFactory.create(use_rag=True)
    db_session.add(a)
    await db_session.commit()
    return a


class TestCreateRun:
    async def test_create_run_missing_target(self, db_session, question_set):
        svc = EvalRunService(db_session)
        with pytest.raises(ValueError):
            await svc.create_run("library", "nope", question_set.id)
        with pytest.raises(ValueError):
            await svc.create_run("agent", "nope", question_set.id)
        with pytest.raises(ValueError):
            await svc.create_run("bogus", "x", question_set.id)

    async def test_create_run_missing_question_set(self, db_session, library):
        with pytest.raises(ValueError):
            await EvalRunService(db_session).create_run("library", library.id, "nope")

    async def test_create_library_run_snapshots_and_enqueues(self, db_session, library,
                                                             question_set):
        run = await EvalRunService(db_session).create_run(
            "library", library.id, question_set.id)
        assert run.status == "pending"
        assert run.run_type == "retrieval"
        assert run.target_label == "ACME Docs"
        snap = run.config_snapshot
        assert snap["library_id"] == library.id
        assert snap["collection_name"] == "kb_acme_runs"
        assert snap["top_k"] == 10
        assert snap["rerank"] is True
        jobs = (await db_session.execute(
            select(Job).where(Job.job_type == "run_scorecard"))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].payload["run_id"] == run.id

    async def test_create_agent_run_snapshot(self, db_session, agent, question_set):
        run = await EvalRunService(db_session).create_run(
            "agent", agent.id, question_set.id)
        assert run.run_type == "answer"
        snap = run.config_snapshot
        assert snap["agent_id"] == agent.id
        assert snap["provider"] == agent.model_provider
        assert snap["model"] == agent.model_name
        assert snap["bound_library_ids"] == []


class TestRetrievalRun:
    async def test_retrieval_run_end_to_end(self, db_session, library, docs,
                                            question_set):
        svc_q = QuestionSetService(db_session)
        await svc_q.add_question(question_set.id, "Where is doc0 covered?",
                                 expected_document_ids=[docs[0].id])
        await svc_q.add_question(question_set.id, "Where is doc1 covered?",
                                 expected_document_ids=[docs[1].id])

        svc = EvalRunService(db_session)
        run = await svc.create_run("library", library.id, question_set.id)

        mock_rag = MagicMock()
        mock_rag.search = AsyncMock(side_effect=[
            [_hit(docs[0].id, 0.95), _hit("other-doc", 0.5)],  # q1: hit at rank 1
            [_hit("other-doc", 0.8)],                          # q2: miss
        ])
        with patch("app.services.evaluation.runner.RAGService", return_value=mock_rag):
            await svc.execute_run(run.id)

        run = await db_session.get(EvalRun, run.id)
        assert run.status == "completed"
        assert run.started_at is not None and run.finished_at is not None
        summary = run.metrics_summary
        assert summary["question_count"] == 2
        assert summary["found_at_5_rate"] == 0.5
        assert summary["mrr"] == 0.5
        assert summary["stale_questions"] == 0

        results = (await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id))).scalars().all()
        assert len(results) == 2
        by_rank = sorted(results, key=lambda r: r.retrieval_metrics["reciprocal_rank"],
                         reverse=True)
        assert by_rank[0].retrieval_metrics["best_rank"] == 1
        assert by_rank[0].retrieved[0]["document_id"] == docs[0].id
        assert by_rank[1].retrieval_metrics["best_rank"] is None
        # Search must hit the production path with the library scope
        call = mock_rag.search.call_args_list[0]
        assert call.kwargs["knowledge_base_id"] == library.id
        assert call.kwargs["top_k"] == 10
        assert call.kwargs["rerank"] is True

    async def test_stale_expected_doc_excluded(self, db_session, library, docs,
                                               question_set):
        svc_q = QuestionSetService(db_session)
        good = await svc_q.add_question(question_set.id, "Valid question?",
                                        expected_document_ids=[docs[0].id])
        bad = await svc_q.add_question(question_set.id, "Stale question?",
                                       expected_document_ids=["deleted-doc-id"])

        svc = EvalRunService(db_session)
        run = await svc.create_run("library", library.id, question_set.id)
        mock_rag = MagicMock()
        mock_rag.search = AsyncMock(return_value=[_hit(docs[0].id)])
        with patch("app.services.evaluation.runner.RAGService", return_value=mock_rag):
            await svc.execute_run(run.id)

        run = await db_session.get(EvalRun, run.id)
        assert run.metrics_summary["stale_questions"] == 1
        assert run.metrics_summary["question_count"] == 1  # stale never scored
        await db_session.refresh(bad)
        assert bad.status == "stale"
        await db_session.refresh(good)
        assert good.status == "active"
        results = (await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id))).scalars().all()
        assert {r.question_id for r in results} == {good.id}


class TestAnswerRun:
    async def _make_answer_run(self, db_session, agent, question_set, docs):
        svc_q = QuestionSetService(db_session)
        await svc_q.add_question(question_set.id, "What is ACME onboarding?",
                                 expected_criteria="Mentions three stages",
                                 expected_document_ids=[docs[0].id])
        svc = EvalRunService(db_session)
        run = await svc.create_run("agent", agent.id, question_set.id)
        return svc, run

    def _mock_agent_query(self, agent_id, docs):
        mock_aq = MagicMock()
        mock_aq.query = AsyncMock(return_value={
            "answer": "ACME onboarding has three stages.",
            "sources": [], "query": "q", "model": "openai/gpt-4",
            "agent_id": agent_id,
            "raw_results": [_hit(docs[0].id, 0.9)],
        })
        return mock_aq

    async def test_answer_run_judge_failure_degrades_to_partial(
            self, db_session, agent, question_set, docs):
        svc, run = await self._make_answer_run(db_session, agent, question_set, docs)
        mock_aq = self._mock_agent_query(agent.id, docs)
        with (patch("app.services.evaluation.runner.AgentQueryService",
                    return_value=mock_aq),
              patch("app.services.evaluation.runner.judge_answer",
                    new=AsyncMock(side_effect=RuntimeError("LLM transport down")))):
            await svc.execute_run(run.id)

        run = await db_session.get(EvalRun, run.id)
        assert run.status == "partial"
        results = (await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id))).scalars().all()
        assert len(results) == 1
        assert results[0].judge_scores is None
        assert results[0].answer_text == "ACME onboarding has three stages."
        # Retrieval metrics still computed from raw results
        assert results[0].retrieval_metrics["best_rank"] == 1
        assert run.metrics_summary["judged_count"] == 0
        # Agent pipeline asked for raw results
        assert mock_aq.query.call_args.kwargs["include_raw_results"] is True

    async def test_answer_run_judged_completes(self, db_session, agent,
                                               question_set, docs):
        svc, run = await self._make_answer_run(db_session, agent, question_set, docs)
        mock_aq = self._mock_agent_query(agent.id, docs)
        judged = {"scores": {"relevance": 0.9, "accuracy": 0.8, "groundedness": 1.0},
                  "passed": True, "rationale": "Covers the three stages."}
        with (patch("app.services.evaluation.runner.AgentQueryService",
                    return_value=mock_aq),
              patch("app.services.evaluation.runner.judge_answer",
                    new=AsyncMock(return_value=judged))):
            await svc.execute_run(run.id)

        run = await db_session.get(EvalRun, run.id)
        assert run.status == "completed"
        assert run.metrics_summary["judged_count"] == 1
        assert run.metrics_summary["passed_count"] == 1
        results = (await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id))).scalars().all()
        assert results[0].judge_scores["accuracy"] == 0.8
        assert results[0].passed is True
        assert results[0].judge_rationale == "Covers the three stages."

    async def test_rejudge_fills_only_null_scores_and_completes(
            self, db_session, agent, question_set, docs):
        svc, run = await self._make_answer_run(db_session, agent, question_set, docs)
        mock_aq = self._mock_agent_query(agent.id, docs)
        with (patch("app.services.evaluation.runner.AgentQueryService",
                    return_value=mock_aq),
              patch("app.services.evaluation.runner.judge_answer",
                    new=AsyncMock(side_effect=RuntimeError("down")))):
            await svc.execute_run(run.id)
        run = await db_session.get(EvalRun, run.id)
        assert run.status == "partial"

        judged = {"scores": {"relevance": 1.0, "accuracy": 1.0, "groundedness": 1.0},
                  "passed": True, "rationale": "Now reachable."}
        with patch("app.services.evaluation.runner.judge_answer",
                   new=AsyncMock(return_value=judged)) as mock_judge:
            await svc.rejudge(run.id)

        run = await db_session.get(EvalRun, run.id)
        assert run.status == "completed"
        assert run.metrics_summary["judged_count"] == 1
        assert mock_judge.await_count == 1  # only the unjudged result
        results = (await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id))).scalars().all()
        assert results[0].judge_scores["relevance"] == 1.0

    async def test_rejudge_rejects_fully_judged_run(self, db_session, agent,
                                                    question_set, docs):
        svc, run = await self._make_answer_run(db_session, agent, question_set, docs)
        mock_aq = self._mock_agent_query(agent.id, docs)
        judged = {"scores": {"relevance": 1.0, "accuracy": 1.0, "groundedness": 1.0},
                  "passed": True, "rationale": "ok"}
        with (patch("app.services.evaluation.runner.AgentQueryService",
                    return_value=mock_aq),
              patch("app.services.evaluation.runner.judge_answer",
                    new=AsyncMock(return_value=judged))):
            await svc.execute_run(run.id)

        with pytest.raises(ValueError):
            await svc.rejudge(run.id)


class TestExperimentRun:
    """target_type='experiment' (slice 3): runs the experiment's agent with
    the experiment's overrides passed through to AgentQueryService.query."""

    @pytest.fixture
    async def experiment(self, db_session, library, agent):
        from app.services.evaluation.experiments import ExperimentService
        # Bind the agent to the library so bound_library_ids is non-trivial
        from app.models import AgentLibrary
        db_session.add(AgentLibrary(agent_id=agent.id, library_id=library.id))
        await db_session.commit()
        return await ExperimentService(db_session).create_experiment(
            library_id=library.id, name="Low temp", agent_id=agent.id,
            overrides={"temperature": 0.2, "rag_top_k": 8})

    async def test_create_experiment_run_snapshot(self, db_session, library, agent,
                                                  question_set, experiment):
        run = await EvalRunService(db_session).create_run(
            "experiment", experiment.id, question_set.id)
        assert run.run_type == "answer"
        assert run.target_type == "experiment"
        assert run.target_label == "Low temp"
        snap = run.config_snapshot
        # Agent snapshot fields present
        assert snap["agent_id"] == agent.id
        assert snap["provider"] == agent.model_provider
        assert snap["model"] == agent.model_name
        assert snap["bound_library_ids"] == [library.id]
        # Plus experiment identity + overrides
        assert snap["experiment_id"] == experiment.id
        assert snap["overrides"] == {"temperature": 0.2, "rag_top_k": 8}
        jobs = (await db_session.execute(
            select(Job).where(Job.job_type == "run_scorecard"))).scalars().all()
        assert jobs[-1].payload["run_id"] == run.id

    async def test_create_run_unknown_experiment(self, db_session, question_set):
        with pytest.raises(ValueError):
            await EvalRunService(db_session).create_run(
                "experiment", "nope", question_set.id)

    async def test_create_run_errored_experiment_rejected(self, db_session,
                                                          question_set, experiment):
        experiment.status = "error"
        await db_session.commit()
        with pytest.raises(ValueError):
            await EvalRunService(db_session).create_run(
                "experiment", experiment.id, question_set.id)

    async def test_create_run_promoted_experiment_allowed(self, db_session,
                                                          question_set, experiment):
        experiment.status = "promoted"
        await db_session.commit()
        run = await EvalRunService(db_session).create_run(
            "experiment", experiment.id, question_set.id)
        assert run.run_type == "answer"

    async def test_execute_passes_overrides_to_agent_query(
            self, db_session, agent, question_set, docs, experiment):
        svc_q = QuestionSetService(db_session)
        await svc_q.add_question(question_set.id, "What is ACME onboarding?",
                                 expected_criteria="Mentions three stages",
                                 expected_document_ids=[docs[0].id])
        svc = EvalRunService(db_session)
        run = await svc.create_run("experiment", experiment.id, question_set.id)

        mock_aq = MagicMock()
        mock_aq.query = AsyncMock(return_value={
            "answer": "Three stages.", "sources": [], "query": "q",
            "model": "openai/gpt-4", "agent_id": agent.id,
            "raw_results": [_hit(docs[0].id, 0.9)],
        })
        judged = {"scores": {"relevance": 1.0, "accuracy": 1.0, "groundedness": 1.0},
                  "passed": True, "rationale": "ok"}
        with (patch("app.services.evaluation.runner.AgentQueryService",
                    return_value=mock_aq),
              patch("app.services.evaluation.runner.judge_answer",
                    new=AsyncMock(return_value=judged))):
            await svc.execute_run(run.id)

        run = await db_session.get(EvalRun, run.id)
        assert run.status == "completed"
        # The query went to the UNDERLYING agent with the experiment overrides
        call = mock_aq.query.await_args
        assert call.args[0] == agent.id
        assert call.kwargs["overrides"] == {"temperature": 0.2, "rag_top_k": 8}


class TestLegacyDocumentResolution:
    """Chunks indexed before library-aware ingestion have no document_id in
    their Qdrant payload — _retrieved_from_results falls back to resolving
    the chunk's source path/url against the library's documents."""

    def test_fallback_resolves_via_source_url(self):
        from app.services.evaluation.runner import _retrieved_from_results

        class FakeResult:
            def __init__(self, source, title):
                self.source = source
                self.title = title
                self.score = 0.5
                self.metadata = {}
                self.document_path = ""

        results = [FakeResult("https://acme.example/guide", "ACME Guide"),
                   FakeResult("https://acme.example/other", "Other")]
        lookup = {"https://acme.example/guide": "doc-123"}
        out = _retrieved_from_results(results, lookup)
        assert out[0]["document_id"] == "doc-123"
        assert out[1]["document_id"] is None

    def test_payload_document_id_wins_over_lookup(self):
        from app.services.evaluation.runner import _retrieved_from_results

        class FakeResult:
            source = "https://acme.example/guide"
            title = "ACME Guide"
            score = 0.5
            metadata = {"document_id": "payload-doc"}
            document_path = ""

        out = _retrieved_from_results([FakeResult()],
                                      {"https://acme.example/guide": "lookup-doc"})
        assert out[0]["document_id"] == "payload-doc"


class TestRetrievedDocIdNormalization:
    """Regression for the 0%-scorecard bug: Qdrant payloads carry the
    human-readable document KEY (documents.document_id, "srcprefix:hash")
    while Question.expected_document_ids stores documents.id UUIDs. Without
    normalizing through doc_lookup, every comparison failed and all library
    scorecards read Found@5=0%, MRR=0.00 on KB-aware indexed content."""

    def test_payload_document_key_normalized_to_uuid(self):
        from app.services.evaluation.runner import _retrieved_from_results

        uuid = "40be0dda-9bb6-4c6b-997f-d37d388640bc"
        doc_lookup = {"221904bf:679ea00e3a890fc1": uuid}
        results = [_hit(document_id="221904bf:679ea00e3a890fc1")]

        retrieved = _retrieved_from_results(results, doc_lookup)
        assert retrieved[0]["document_id"] == uuid

    def test_already_uuid_payload_passes_through(self):
        from app.services.evaluation.runner import _retrieved_from_results

        uuid = "40be0dda-9bb6-4c6b-997f-d37d388640bc"
        retrieved = _retrieved_from_results([_hit(document_id=uuid)], {})
        assert retrieved[0]["document_id"] == uuid

    def test_missing_payload_id_still_resolves_via_source(self):
        from app.services.evaluation.runner import _retrieved_from_results

        uuid = "40be0dda-9bb6-4c6b-997f-d37d388640bc"
        hit = _hit(document_id="ignored")
        hit.metadata = {"source_id": "s1", "title": "ACME Guide"}
        retrieved = _retrieved_from_results(
            [hit], {"https://example.com/doc": uuid})
        assert retrieved[0]["document_id"] == uuid
