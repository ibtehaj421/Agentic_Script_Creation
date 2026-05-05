"""POST /generate — kicks off a new pipeline run.
POST /rerun/{phase}/{job_id} — targeted phase re-run (audio | video | story).
GET  /state/{job_id} — current pipeline state snapshot.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.audio_agent import run_audio_phase
from agents.orchestrator import run_full_pipeline
from agents.story_agent import run_story_phase
from agents.video_agent import run_video_phase
from shared.schemas import PipelineState
from state_manager import StateManager

from ..services.job_runner import new_job_id, register_job, run_blocking

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str
    num_scenes: int = Field(3, ge=1, le=8)
    style: str = "cinematic"


class GenerateResponse(BaseModel):
    job_id: str


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    job_id = new_job_id()
    register_job(job_id, title=req.prompt[:60])
    state = PipelineState(job_id=job_id, prompt=req.prompt, num_scenes=req.num_scenes, style=req.style)

    async def _go():
        await run_blocking(job_id, run_full_pipeline, state)

    asyncio.create_task(_go())
    return GenerateResponse(job_id=job_id)


@router.get("/state/{job_id}")
async def get_state(job_id: str):
    mgr = StateManager()
    ps = mgr.latest(job_id)
    if not ps:
        raise HTTPException(404, "no state for this job_id")
    return ps.model_dump(mode="json")


class RerunResponse(BaseModel):
    ok: bool
    job_id: str


@router.post("/rerun/{phase}/{job_id}", response_model=RerunResponse)
async def rerun_phase(phase: str, job_id: str):
    mgr = StateManager()
    ps = mgr.latest(job_id)
    if not ps:
        raise HTTPException(404, "no state for this job_id")

    handlers = {
        "story": run_story_phase,
        "audio": run_audio_phase,
        "video": run_video_phase,
    }
    handler = handlers.get(phase)
    if not handler:
        raise HTTPException(400, f"unknown phase {phase}")

    def _do():
        new_state = handler(ps)
        snap = mgr.snapshot(
            new_state,
            changed_phase=phase,
            change_summary=f"Re-ran phase {phase}",
            triggered_by="rerun",
        )
        return {"version": snap.version}

    asyncio.create_task(run_blocking(job_id, _do))
    return RerunResponse(ok=True, job_id=job_id)
