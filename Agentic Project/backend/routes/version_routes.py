"""Versioning REST surface for Phase 5."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from state_manager import StateManager

router = APIRouter()


@router.get("/versions/{job_id}")
async def list_versions(job_id: str):
    mgr = StateManager()
    return mgr.history(job_id)


@router.get("/versions/{job_id}/{version}")
async def get_version(job_id: str, version: int):
    mgr = StateManager()
    ps = mgr.get(job_id, version)
    if not ps:
        raise HTTPException(404, "version not found")
    return ps.model_dump(mode="json")


@router.post("/undo/{job_id}")
async def undo(job_id: str, to_version: int | None = None):
    """Move the active-version pointer backwards. With explicit
    `to_version` we jump there; without, we go to the parent of the
    currently active version (i.e. true "undo last edit"). Either way
    no new row is inserted."""
    mgr = StateManager()
    if to_version is None:
        active = mgr.active_version(job_id)
        if active is None:
            raise HTTPException(404, "no versions")
        target_state = mgr.storage.get(job_id, active)
        parent = getattr(target_state, "parent_version", None) if target_state else None
        if parent is None:
            raise HTTPException(400, "active version has no parent; nothing to undo")
        to_version = parent
    return mgr.revert(job_id, to_version)


@router.get("/jobs")
async def list_jobs():
    mgr = StateManager()
    return mgr.history_idx.list_all_jobs()
