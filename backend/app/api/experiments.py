"""Experiments API — library-scoped pipeline experiments (design doc §4).

Create an agent-anchored override set, compare it against the agent's
baseline on a question set (two scorecard runs + verdict), and promote the
winner into the agent's live config. Replaces the removed source-scoped
experiments backend (slice 3); index experiments arrive in Slice 4.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services.evaluation import (
    ExperimentService, load_comparison, start_comparison,
)

router = APIRouter()


class ExperimentCreate(BaseModel):
    library_id: str
    agent_id: str
    name: str
    description: Optional[str] = None
    overrides: dict


class ExperimentResponse(BaseModel):
    id: str
    library_id: str
    agent_id: Optional[str]
    name: str
    description: Optional[str]
    experiment_type: str
    overrides: dict
    status: str
    error_message: Optional[str]
    created_at: datetime
    promoted_at: Optional[datetime]

    class Config:
        from_attributes = True


class CompareRequest(BaseModel):
    question_set_id: str


def _service_error(e: ValueError) -> HTTPException:
    status = 404 if "not found" in str(e).lower() else 400
    return HTTPException(status_code=status, detail=str(e))


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(library_id: Optional[str] = Query(None),
                           agent_id: Optional[str] = Query(None),
                           db: AsyncSession = Depends(get_db),
                           _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    return await ExperimentService(db).list_experiments(
        library_id=library_id, agent_id=agent_id)


@router.post("", response_model=ExperimentResponse, status_code=201)
async def create_experiment(body: ExperimentCreate,
                            db: AsyncSession = Depends(get_db),
                            _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    try:
        return await ExperimentService(db).create_experiment(
            library_id=body.library_id, name=body.name, agent_id=body.agent_id,
            overrides=body.overrides, description=body.description)
    except ValueError as e:
        raise _service_error(e)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, db: AsyncSession = Depends(get_db),
                         _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    exp = await ExperimentService(db).get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.delete("/{experiment_id}", status_code=204)
async def delete_experiment(experiment_id: str, db: AsyncSession = Depends(get_db),
                            _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    if not await ExperimentService(db).delete_experiment(experiment_id):
        raise HTTPException(status_code=404, detail="Experiment not found")


@router.post("/{experiment_id}/compare", status_code=202)
async def compare_experiment(experiment_id: str, body: CompareRequest,
                             db: AsyncSession = Depends(get_db),
                             _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    """Enqueue the baseline + experiment scorecard run pair."""
    try:
        return await start_comparison(db, experiment_id, body.question_set_id)
    except ValueError as e:
        raise _service_error(e)


@router.get("/{experiment_id}/comparison")
async def get_comparison(experiment_id: str,
                         baseline_run_id: str = Query(...),
                         experiment_run_id: str = Query(...),
                         db: AsyncSession = Depends(get_db),
                         _auth: Optional[APIKey] = Depends(require_scope(Scope.READ))):
    """Verdict JSON for a finished compare pair. 404 if either run is
    missing, 409 if either has not finished (completed/partial)."""
    if not await ExperimentService(db).get_experiment(experiment_id):
        raise HTTPException(status_code=404, detail="Experiment not found")
    try:
        return await load_comparison(db, baseline_run_id, experiment_run_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{experiment_id}/promote", response_model=ExperimentResponse)
async def promote_experiment(experiment_id: str,
                             db: AsyncSession = Depends(get_db),
                             _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE))):
    try:
        return await ExperimentService(db).promote(experiment_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=409, detail=str(e))
