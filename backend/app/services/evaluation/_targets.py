"""Scorecard target resolution — validate a run target and snapshot its config.

Split out of runner.py (line budget): one function per target type, returning
(run_type, target_label, config_snapshot). Raises ValueError on unknown or
unrunnable targets.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, AgentLibrary, Experiment, Library

RETRIEVAL_TOP_K = 10


async def _agent_snapshot(db: AsyncSession, agent: Agent) -> dict:
    bound = (await db.execute(
        select(AgentLibrary.library_id)
        .where(AgentLibrary.agent_id == agent.id)
    )).scalars().all()
    return {
        "agent_id": agent.id,
        "provider": agent.model_provider,
        "model": agent.model_name,
        "temperature": agent.temperature,
        "use_rag": agent.use_rag,
        "rag_top_k": agent.rag_top_k,
        "bound_library_ids": list(bound),
    }


async def resolve_target(db: AsyncSession, target_type: str,
                         target_id: str) -> tuple[str, str, dict]:
    """Resolve (run_type, target_label, config_snapshot) for a run target."""
    if target_type == "library":
        lib = await db.get(Library, target_id)
        if not lib:
            raise ValueError(f"Library not found: {target_id}")
        return "retrieval", lib.name, {
            "library_id": lib.id,
            "collection_name": lib.collection_name,
            "embedding_provider": lib.embedding_provider,
            "embedding_model": lib.embedding_model,
            "top_k": RETRIEVAL_TOP_K,
            "rerank": True,
        }

    if target_type == "agent":
        agent = await db.get(Agent, target_id)
        if not agent:
            raise ValueError(f"Agent not found: {target_id}")
        return "answer", agent.name, await _agent_snapshot(db, agent)

    if target_type == "experiment":
        exp = await db.get(Experiment, target_id)
        if not exp:
            raise ValueError(f"Experiment not found: {target_id}")
        if exp.status not in ("ready", "promoted"):
            raise ValueError(
                f"Experiment is not runnable (status: {exp.status})")
        agent = await db.get(Agent, exp.agent_id) if exp.agent_id else None
        if not agent:
            raise ValueError(f"Agent not found: {exp.agent_id}")
        config = await _agent_snapshot(db, agent)
        config["experiment_id"] = exp.id
        config["overrides"] = exp.overrides or {}
        return "answer", exp.name, config

    raise ValueError(f"Invalid target_type: {target_type}")
