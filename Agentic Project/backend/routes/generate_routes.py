"""POST /generate — kicks off a new pipeline run.
POST /rerun/{phase}/{job_id} — targeted phase re-run (audio | video | story).
GET  /state/{job_id} — current pipeline state snapshot.
"""
from __future__ import annotations

import asyncio
import secrets
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.audio_agent import run_audio_phase
from agents.orchestrator import run_full_pipeline
from agents.story_agent import run_story_phase
from agents.video_agent import run_video_phase
from shared.schemas import PipelineState
from shared.utils import clear_phase_cache
from state_manager import StateManager

from ..services.job_runner import new_job_id, register_job, run_blocking

router = APIRouter()


_VARIATION_DIRECTIVES = [
    "Try a fresh angle on this story — different dialogue rhythm, different power dynamic between characters.",
    "Take a more visceral, character-driven approach. Lean into the emotional beats and surprise me.",
    "Same world but different scenes and lines — vary the pacing and avoid the obvious dialogue choices.",
    "Reimagine the script with sharper, more naturalistic dialogue. Lean into subtext and pauses.",
]


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
async def rerun_phase(phase: str, job_id: str, force: bool = True):
    """Re-run a phase, cascading downstream when the upstream changed.

    With `force=true` (default for manual UI reruns) the per-job tool
    cache is wiped and the phase regenerates fresh outputs. Cascading
    rules:
      * story → also rebuild audio + video, since new dialogue makes
        the existing TTS wavs and scene composites stale.
      * audio → also rebuild video, since new wavs change line durations
        and the close-ups baked against the old wavs.
      * video → terminal phase, just rebuild it.

    The story phase additionally gets a random variation directive
    layered onto the prompt — the Groq calls in text_generator already
    run at temperature ≥0.5, but the directive nudges the model further
    so reruns feel meaningfully different rather than slight rewordings.

    Edit-agent automatic reruns pass force=false to keep cache hits and
    skip the cascade — that path knows exactly which assets it touched.
    """
    mgr = StateManager()
    ps = mgr.latest(job_id)
    if not ps:
        raise HTTPException(404, "no state for this job_id")

    if phase not in {"story", "audio", "video"}:
        raise HTTPException(400, f"unknown phase {phase}")

    cascade: list[str]
    if not force:
        cascade = [phase]
    elif phase == "story":
        cascade = ["story", "audio", "video"]
    elif phase == "audio":
        cascade = ["audio", "video"]
    else:
        cascade = ["video"]

    if force:
        clear_phase_cache(phase, ps)

    def _do():
        state = ps
        for p in cascade:
            if p == "story":
                directive = secrets.choice(_VARIATION_DIRECTIVES) if force else ""
                state = run_story_phase(state, directive=directive)
            elif p == "audio":
                state = run_audio_phase(state)
            else:
                state = run_video_phase(state)
        summary = (
            f"Force-regenerated {phase}"
            + (f" (cascaded {' → '.join(cascade)})" if force and len(cascade) > 1 else "")
            if force
            else f"Re-ran phase {phase}"
        )
        snap = mgr.snapshot(
            state,
            changed_phase=phase,
            change_summary=summary,
            triggered_by="rerun",
        )
        return {"version": snap.version}

    asyncio.create_task(run_blocking(job_id, _do))
    return RerunResponse(ok=True, job_id=job_id)
