"""Phase 3 output — per-scene clips + the final composited MP4."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SceneClip(BaseModel):
    scene_id: int
    background_path: Optional[str] = None  # still image used as scene backdrop
    raw_clip_path: Optional[str] = None     # ken-burns zoom without audio
    composed_path: Optional[str] = None     # with portrait + subtitles + audio
    duration_s: float = 0.0


class VideoOutput(BaseModel):
    scene_clips: Dict[int, SceneClip] = Field(default_factory=dict)
    final_mp4: Optional[str] = None
    subtitles_burned: bool = True
    transitions: str = "crossfade"
