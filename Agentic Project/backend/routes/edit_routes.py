"""POST /edit/{job_id} — run the edit agent on a free-text query."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.edit_agent import EditAgent
from state_manager import StateManager

from ..services.job_runner import run_blocking

router = APIRouter()


class EditRequest(BaseModel):
    query: str


class EditResponse(BaseModel):
    ok: bool
    job_id: str


@router.post("/edit/{job_id}", response_model=EditResponse)
async def edit(job_id: str, req: EditRequest):
    mgr = StateManager()
    ps = mgr.latest(job_id)
    if not ps:
        raise HTTPException(404, "no state for this job_id")

    agent = EditAgent(persist=False)

    def _do():
        result, new_state = agent.run(req.query, ps, thread_id=job_id)
        return result.model_dump()

    asyncio.create_task(run_blocking(job_id, _do))
    return EditResponse(ok=True, job_id=job_id)
