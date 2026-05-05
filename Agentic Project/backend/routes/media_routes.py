"""Thin layer over the /media static mount for the UI to introspect a job's files."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import OUTPUTS_DIR
from state_manager import StateManager

router = APIRouter()


@router.get("/outputs/{job_id}")
async def list_outputs(job_id: str):
    mgr = StateManager()
    ps = mgr.latest(job_id)
    if not ps:
        raise HTTPException(404, "no state for job")
    return {
        "final_mp4": _media_url(ps.video.final_mp4),
        "scenes": {
            sid: {
                "background": _media_url(c.background_path),
                "composed": _media_url(c.composed_path),
            }
            for sid, c in sorted(ps.video.scene_clips.items())
        },
        "character_portraits": {
            c.name: _media_url(c.image_path) for c in ps.story.characters if c.image_path
        },
    }


def _media_url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return None
    return f"/media/{rel.as_posix()}"
