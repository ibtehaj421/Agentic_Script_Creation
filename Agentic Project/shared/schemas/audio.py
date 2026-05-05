"""Phase 2 output — TTS segments + per-scene timing manifest."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AudioSegment(BaseModel):
    """One dialogue line rendered to audio."""

    scene_id: int
    speaker: str
    line: str
    audio_file: str
    start_ms: int = 0
    end_ms: int = 0
    emotion: str = "neutral"


class TimingManifest(BaseModel):
    """Matches the spec: { scene_id, audio_file, start_ms, end_ms } with BGM ref."""

    segments: List[AudioSegment] = Field(default_factory=list)
    scene_audio: dict[int, str] = Field(default_factory=dict)  # scene_id -> merged wav
    scene_durations_ms: dict[int, int] = Field(default_factory=dict)
    bgm_tracks: dict[int, str] = Field(default_factory=dict)  # scene_id -> bgm wav
