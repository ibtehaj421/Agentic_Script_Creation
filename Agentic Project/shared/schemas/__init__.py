"""Pydantic schemas defining the shared JSON state contract across all five phases.

Import from here (not the individual files) so downstream modules have one
stable import path: `from shared.schemas import PipelineState, ...`
"""
from .story import Character, DialogueTurn, Scene, StoryState
from .audio import AudioSegment, TimingManifest
from .video import SceneClip, VideoOutput
from .pipeline import PhaseStatus, PipelineState, VersionSnapshot
from .edit import EditIntent, EditResult, EditTarget

__all__ = [
    "Character",
    "DialogueTurn",
    "Scene",
    "StoryState",
    "AudioSegment",
    "TimingManifest",
    "SceneClip",
    "VideoOutput",
    "PhaseStatus",
    "PipelineState",
    "VersionSnapshot",
    "EditIntent",
    "EditResult",
    "EditTarget",
]
