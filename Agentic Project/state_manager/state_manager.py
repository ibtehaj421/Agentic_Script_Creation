"""Top-level state manager.

Contract (matches the spec's recommended pattern):

    mgr.snapshot(state, changed_phase=..., change_summary=..., triggered_by=...)
        -> persists a new version + freezes referenced assets
    mgr.revert(version) -> restores assets + returns the restored state dict
    mgr.history(job_id)  -> list of version descriptors for the UI
"""
from __future__ import annotations

import json
from typing import Any, Iterable, List, Optional

from shared.schemas import PipelineState, VersionSnapshot
from shared.utils import timestamp_ms

from .history import HistoryIndex
from .snapshot import SnapshotStore
from .storage import VersionStorage


class StateManager:
    def __init__(self) -> None:
        self.storage = VersionStorage()
        self.snapshots = SnapshotStore()
        self.history_idx = HistoryIndex(self.storage)

    # ── Write side ─────────────────────────────────────────────────────
    def snapshot(
        self,
        state: PipelineState | dict,
        changed_phase: str = "",
        change_summary: str = "",
        triggered_by: str = "pipeline",
    ) -> VersionSnapshot:
        """Append a new version. parent_version is whatever the active
        pointer was at snapshot time, giving us git-style branching when
        new edits are made after an undo."""
        state_obj = state if isinstance(state, PipelineState) else PipelineState(**state)
        parent = self.storage.get_active(state_obj.job_id)
        if parent is None:
            # Legacy job created before the active-version pointer
            # existed — chain off the highest existing version so we
            # don't create an orphan root.
            prev = self.storage.latest(state_obj.job_id)
            parent = prev.version if prev else None
        version = self.storage.next_version(state_obj.job_id)
        state_obj.version = version
        asset_paths = _collect_asset_paths(state_obj)
        asset_dir = self.snapshots.freeze(state_obj.job_id, version, asset_paths)

        snap = VersionSnapshot(
            version=version,
            parent_version=parent,
            job_id=state_obj.job_id,
            timestamp_ms=timestamp_ms(),
            state_json=state_obj.model_dump_json(),
            asset_dir=str(asset_dir),
            changed_phase=changed_phase,
            change_summary=change_summary,
            triggered_by=triggered_by,
        )
        self.storage.insert(snap)
        # New edits become the active version automatically.
        self.storage.set_active(state_obj.job_id, version)
        return snap

    # ── Read side ──────────────────────────────────────────────────────
    def latest(self, job_id: str) -> Optional[PipelineState]:
        """Return the *active* version's state. Falls back to highest
        version number if the active pointer hasn't been set yet (legacy
        DBs from before the active-pointer migration)."""
        active_v = self.storage.get_active(job_id)
        if active_v is not None:
            s = self.storage.get(job_id, active_v)
        else:
            s = self.storage.latest(job_id)
        return PipelineState(**json.loads(s.state_json)) if s else None

    def get(self, job_id: str, version: int) -> Optional[PipelineState]:
        s = self.storage.get(job_id, version)
        return PipelineState(**json.loads(s.state_json)) if s else None

    def active_version(self, job_id: str) -> Optional[int]:
        v = self.storage.get_active(job_id)
        if v is not None:
            return v
        s = self.storage.latest(job_id)
        return s.version if s else None

    def history(self, job_id: str) -> List[dict]:
        return self.history_idx.list_for_job(job_id)

    def lineage(self, job_id: str, version: Optional[int] = None) -> List[int]:
        """Walk parent_version pointers from `version` (or active) back to
        the root, returning a list ordered child→parent. Stops on first
        loop or NULL parent. Handy for the UI to draw the lineage chain."""
        v = version if version is not None else self.active_version(job_id)
        chain: List[int] = []
        seen: set[int] = set()
        while v is not None and v not in seen:
            chain.append(v)
            seen.add(v)
            row = self.storage.get(job_id, v)
            if not row:
                break
            v = row.parent_version
        return chain

    # ── Undo / revert ──────────────────────────────────────────────────
    def revert(self, job_id: str, version: int) -> dict[str, Any]:
        """Move the active-version pointer to `version` and restore its
        frozen assets to the working tree. **Does not insert a new row** —
        undo is a pointer move, not a new edit. Subsequent edits will
        branch from this version (their parent_version will be `version`).
        """
        target = self.storage.get(job_id, version)
        if not target:
            raise KeyError(f"Unknown version {version} for job {job_id!r}")

        restored_paths = self.snapshots.restore(job_id, version)
        self.storage.set_active(job_id, version)
        return {
            "ok": True,
            "active_version": version,
            "restored_paths": restored_paths,
            "state": json.loads(target.state_json),
        }


def _collect_asset_paths(state: PipelineState) -> Iterable[str]:
    """Walk the PipelineState and yield every file-path referenced."""
    paths: list[str] = []
    # Character images
    for c in state.story.characters:
        if c.image_path:
            paths.append(c.image_path)
    # Audio segments + merged scene audio + BGM
    for seg in state.audio.segments:
        paths.append(seg.audio_file)
    paths.extend(state.audio.scene_audio.values())
    paths.extend(state.audio.bgm_tracks.values())
    # Video: backgrounds, raw clips, composed per-scene, final
    for clip in state.video.scene_clips.values():
        for p in (clip.background_path, clip.raw_clip_path, clip.composed_path):
            if p:
                paths.append(p)
    if state.video.final_mp4:
        paths.append(state.video.final_mp4)
    return paths
