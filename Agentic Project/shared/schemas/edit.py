"""Phase 5 intent schema — what the LLM classifier emits."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EditTarget(str, Enum):
    """Which artefact the edit operates on. Maps to which phase re-runs."""

    AUDIO = "audio"
    VIDEO_FRAME = "video_frame"  # re-runs image generation for targeted scenes
    VIDEO = "video"              # re-composites without regenerating assets
    SCRIPT = "script"            # re-runs phase 1 (cascades downstream)


class EditIntent(BaseModel):
    """LLM-classified edit intent. This is the contract Phase 5 hinges on."""

    intent: str                                      # e.g. "change_voice_tone"
    target: EditTarget
    scope: str = ""                                  # e.g. "character:Narrator", "scene:2"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    raw_query: str = ""


class EditResult(BaseModel):
    """Outcome of executing an EditIntent."""

    ok: bool
    intent: EditIntent
    new_version: int = 0
    message: str = ""
    affected_scenes: list[int] = Field(default_factory=list)
