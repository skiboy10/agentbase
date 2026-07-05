"""Pipeline experiment lifecycle: create, list, promote (design doc §4).

Slice 3 scope: experiment_type='pipeline' only — an agent-anchored set of
query-time config overrides scored against a question set, promotable into
the agent's live config. Index experiments (shadow collection rebuilds)
arrive in Slice 4.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Agent, Experiment, Library

logger = structlog.get_logger()

# Contract: override keys are Agent column names verbatim — these are exactly
# the fields the production query path (AgentQueryService) reads.
PIPELINE_OVERRIDABLE = {"system_prompt", "model_provider", "model_name",
                        "temperature", "rag_top_k"}


class ExperimentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_experiment(self, library_id: str, name: str,
                                agent_id: Optional[str],
                                overrides: Optional[dict],
                                description: Optional[str] = None,
                                experiment_type: str = "pipeline") -> Experiment:
        if experiment_type == "index":
            raise ValueError("Index experiments arrive in a later release")
        if experiment_type != "pipeline":
            raise ValueError(f"Invalid experiment_type: {experiment_type}")
        if not await self.db.get(Library, library_id):
            raise ValueError(f"Library not found: {library_id}")
        if not agent_id:
            raise ValueError("Pipeline experiments require agent_id")
        if not await self.db.get(Agent, agent_id):
            raise ValueError(f"Agent not found: {agent_id}")
        if not overrides:
            raise ValueError("Pipeline experiments require at least one override")
        unknown = set(overrides) - PIPELINE_OVERRIDABLE
        if unknown:
            raise ValueError(
                f"Non-overridable keys: {', '.join(sorted(unknown))} "
                f"(allowed: {', '.join(sorted(PIPELINE_OVERRIDABLE))})")

        exp = Experiment(
            library_id=library_id,
            agent_id=agent_id,
            name=name,
            description=description,
            experiment_type=experiment_type,
            overrides=overrides,
            status="ready",  # pipeline experiments need no indexing
        )
        self.db.add(exp)
        await self.db.commit()
        await self.db.refresh(exp)
        return exp

    async def list_experiments(self, library_id: Optional[str] = None,
                               agent_id: Optional[str] = None) -> list[Experiment]:
        stmt = select(Experiment).order_by(Experiment.created_at.desc())
        if library_id:
            stmt = stmt.where(Experiment.library_id == library_id)
        if agent_id:
            stmt = stmt.where(Experiment.agent_id == agent_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        return await self.db.get(Experiment, experiment_id)

    async def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment (promoted ones included — scorecard history
        lives in EvalRuns, not on the experiment row)."""
        exp = await self.db.get(Experiment, experiment_id)
        if not exp:
            return False
        await self.db.delete(exp)
        await self.db.commit()
        return True

    async def promote(self, experiment_id: str) -> Experiment:
        """Apply a ready experiment's overrides to its agent's live config."""
        exp = await self.db.get(Experiment, experiment_id)
        if not exp:
            raise ValueError(f"Experiment not found: {experiment_id}")
        if exp.status != "ready":
            raise ValueError(
                f"Only 'ready' experiments can be promoted (status: {exp.status})")
        agent = await self.db.get(Agent, exp.agent_id) if exp.agent_id else None
        if not agent:
            raise ValueError(f"Agent not found: {exp.agent_id}")

        for key, value in (exp.overrides or {}).items():
            setattr(agent, key, value)
        exp.status = "promoted"
        exp.promoted_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(exp)

        from app.core.events import event_bus
        await event_bus.publish(
            event_type="evaluation.experiment_promoted",
            payload={"experiment_id": exp.id, "agent_id": agent.id,
                     "library_id": exp.library_id},
            source="system",
        )
        logger.info("Experiment promoted", experiment_id=exp.id,
                    agent_id=agent.id, overrides=list((exp.overrides or {}).keys()))
        return exp
