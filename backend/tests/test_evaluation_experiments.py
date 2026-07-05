"""Tests for ExperimentService — pipeline experiments (create/list/promote).

Slice 3: pipeline experiments are agent-anchored query-time override sets;
no indexing happens, so experiments are 'ready' at creation. Index
experiments (shadow collections) arrive in Slice 4 and are rejected here.
"""
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Experiment, Library
from app.services.evaluation.experiments import (
    PIPELINE_OVERRIDABLE, ExperimentService,
)
from tests.factories import AgentFactory


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_exp",
                  embedding_provider="ollama", embedding_model="qwen3-embedding:4b")
    db_session.add(lib)
    await db_session.commit()
    return lib


@pytest.fixture
async def agent(db_session: AsyncSession) -> Agent:
    a = AgentFactory.create(use_rag=True, temperature=0.7, rag_top_k=5)
    db_session.add(a)
    await db_session.commit()
    return a


class TestCreateExperiment:
    async def test_create_pipeline_experiment_ready(self, db_session, library, agent):
        svc = ExperimentService(db_session)
        exp = await svc.create_experiment(
            library_id=library.id, name="Low temp", agent_id=agent.id,
            overrides={"temperature": 0.2, "rag_top_k": 8})
        assert exp.id
        assert exp.experiment_type == "pipeline"
        assert exp.status == "ready"  # no indexing for pipeline experiments
        assert exp.overrides == {"temperature": 0.2, "rag_top_k": 8}
        assert exp.library_id == library.id
        assert exp.agent_id == agent.id

    async def test_create_unknown_library(self, db_session, agent):
        with pytest.raises(ValueError):
            await ExperimentService(db_session).create_experiment(
                library_id="nope", name="x", agent_id=agent.id,
                overrides={"temperature": 0.2})

    async def test_create_unknown_agent(self, db_session, library):
        with pytest.raises(ValueError):
            await ExperimentService(db_session).create_experiment(
                library_id=library.id, name="x", agent_id="nope",
                overrides={"temperature": 0.2})

    async def test_create_pipeline_requires_agent(self, db_session, library):
        with pytest.raises(ValueError):
            await ExperimentService(db_session).create_experiment(
                library_id=library.id, name="x", agent_id=None,
                overrides={"temperature": 0.2})

    async def test_create_non_overridable_key_rejected(self, db_session, library,
                                                       agent):
        with pytest.raises(ValueError, match="chunk_size"):
            await ExperimentService(db_session).create_experiment(
                library_id=library.id, name="x", agent_id=agent.id,
                overrides={"chunk_size": 512})

    async def test_create_requires_at_least_one_override(self, db_session, library,
                                                         agent):
        with pytest.raises(ValueError):
            await ExperimentService(db_session).create_experiment(
                library_id=library.id, name="x", agent_id=agent.id, overrides={})

    async def test_index_type_rejected_for_now(self, db_session, library, agent):
        with pytest.raises(ValueError, match="later release"):
            await ExperimentService(db_session).create_experiment(
                library_id=library.id, name="x", agent_id=agent.id,
                overrides={"temperature": 0.2}, experiment_type="index")

    def test_overridable_keys_match_agent_columns(self):
        # Contract: override keys are Agent column names verbatim.
        assert PIPELINE_OVERRIDABLE == {"system_prompt", "model_provider",
                                        "model_name", "temperature", "rag_top_k"}


class TestListGetDelete:
    async def test_list_by_library_and_agent(self, db_session, library, agent):
        svc = ExperimentService(db_session)
        other_lib = Library(name="Other", collection_name="kb_other")
        db_session.add(other_lib)
        await db_session.commit()
        e1 = await svc.create_experiment(library_id=library.id, name="A",
                                         agent_id=agent.id,
                                         overrides={"temperature": 0.1})
        await svc.create_experiment(library_id=other_lib.id, name="B",
                                    agent_id=agent.id,
                                    overrides={"temperature": 0.3})
        in_lib = await svc.list_experiments(library_id=library.id)
        assert [e.id for e in in_lib] == [e1.id]
        by_agent = await svc.list_experiments(agent_id=agent.id)
        assert len(by_agent) == 2

    async def test_get_and_delete(self, db_session, library, agent):
        svc = ExperimentService(db_session)
        exp = await svc.create_experiment(library_id=library.id, name="A",
                                          agent_id=agent.id,
                                          overrides={"rag_top_k": 3})
        assert (await svc.get_experiment(exp.id)).id == exp.id
        assert await svc.delete_experiment(exp.id) is True
        assert await svc.get_experiment(exp.id) is None
        assert await svc.delete_experiment("nope") is False


class TestPromote:
    async def test_promote_applies_overrides_and_preserves_rest(
            self, db_session, library, agent):
        svc = ExperimentService(db_session)
        original_prompt = agent.system_prompt
        original_model = agent.model_name
        exp = await svc.create_experiment(
            library_id=library.id, name="Tuned", agent_id=agent.id,
            overrides={"temperature": 0.15, "rag_top_k": 9})

        with patch("app.core.events.event_bus.publish",
                   new_callable=AsyncMock) as mock_pub:
            promoted = await svc.promote(exp.id)

        assert promoted.status == "promoted"
        assert promoted.promoted_at is not None
        agent_row = await db_session.get(Agent, agent.id)
        assert agent_row.temperature == 0.15
        assert agent_row.rag_top_k == 9
        # Untouched fields preserved
        assert agent_row.system_prompt == original_prompt
        assert agent_row.model_name == original_model
        # SSE event emitted
        mock_pub.assert_awaited_once()
        kwargs = mock_pub.await_args.kwargs
        assert kwargs["event_type"] == "evaluation.experiment_promoted"
        assert kwargs["payload"] == {"experiment_id": exp.id,
                                     "agent_id": agent.id,
                                     "library_id": library.id}

    async def test_promote_non_ready_rejected(self, db_session, library, agent):
        svc = ExperimentService(db_session)
        exp = await svc.create_experiment(
            library_id=library.id, name="Once", agent_id=agent.id,
            overrides={"temperature": 0.5})
        with patch("app.core.events.event_bus.publish", new_callable=AsyncMock):
            await svc.promote(exp.id)
        with pytest.raises(ValueError):
            await svc.promote(exp.id)

    async def test_promote_unknown_experiment(self, db_session):
        with pytest.raises(ValueError):
            await ExperimentService(db_session).promote("nope")

    async def test_delete_promoted_experiment_allowed(self, db_session, library,
                                                      agent):
        # History lives in EvalRuns — deleting a promoted experiment is fine.
        svc = ExperimentService(db_session)
        exp = await svc.create_experiment(
            library_id=library.id, name="Done", agent_id=agent.id,
            overrides={"temperature": 0.4})
        with patch("app.core.events.event_bus.publish", new_callable=AsyncMock):
            await svc.promote(exp.id)
        assert await svc.delete_experiment(exp.id) is True
        assert await db_session.get(Experiment, exp.id) is None
