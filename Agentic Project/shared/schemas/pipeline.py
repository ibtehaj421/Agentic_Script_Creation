"""Top-level pipeline state + versioning record.

This is the JSON object the state manager snapshots on every write.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .audio import TimingManifest
from .story import StoryState
from .video import VideoOutput


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineState(BaseModel):
    """Shared JSON state that flows through every phase."""

    job_id: str
    prompt: str
    num_scenes: int = 3
    style: str = "cinematic"

    story: StoryState = Field(default_factory=StoryState)
    audio: TimingManifest = Field(default_factory=TimingManifest)
    video: VideoOutput = Field(default_factory=VideoOutput)

    phase_status: Dict[str, PhaseStatus] = Field(
        default_factory=lambda: {
            "story": PhaseStatus.PENDING,
            "audio": PhaseStatus.PENDING,
            "video": PhaseStatus.PENDING,
        }
    )

    version: int = 0
    errors: List[str] = Field(default_factory=list)
    log: List[str] = Field(default_factory=list)


class VersionSnapshot(BaseModel):
    """One immutable row in the versions log (state + pointers to assets)."""

    version: int
    job_id: str
    timestamp_ms: int
    state_json: str              # serialized PipelineState for this version
    asset_dir: str               # directory holding the frozen asset copies
    changed_phase: str = ""      # which phase the change touched (story/audio/video/edit)
    change_summary: str = ""     # human-readable diff summary for the UI
    triggered_by: str = "pipeline"  # pipeline | edit | rerun | undo
    # Which version this one was made FROM. Lets the UI render the active
    # version's lineage (e.g. v4 → v2 → v1 if v4 was created after undoing
    # v3 back to v2 and editing). NULL for v1 / pre-fix rows.
    parent_version: Optional[int] = None
