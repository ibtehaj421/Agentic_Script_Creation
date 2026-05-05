"""Phase 1 output — story, scenes, characters.

Matches the spec's `{ story, scenes[], characters[] }` structure exactly so
all downstream phases can consume without translation.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DialogueTurn(BaseModel):
    speaker: str
    line: str
    visual_cue: str = ""
    emotion: str = "neutral"


class Scene(BaseModel):
    scene_id: int
    location: str
    action: str
    characters: List[str] = Field(default_factory=list)
    dialogue: List[DialogueTurn] = Field(default_factory=list)
    duration_s: float = 0.0  # filled by audio phase once TTS lengths known
    mood: str = "neutral"


class Character(BaseModel):
    name: str
    role: str = ""
    personality_traits: List[str] = Field(default_factory=list)
    appearance: str = ""
    voice_style: str = "neutral"
    # Used by the TTS voice picker to gender-filter the voice pool so a
    # female character doesn't land on a male voice via hash collision or
    # style-override mismatch.
    gender: str = "neutral"  # one of: "male" | "female" | "neutral"
    reference_style: str = "cinematic"
    image_path: Optional[str] = None  # set after image generation
    stock_refs: List[dict] = Field(default_factory=list)


class StoryState(BaseModel):
    """Phase 1 canonical output."""

    title: str = ""
    logline: str = ""
    prompt: str = ""
    language: str = "en"
    scenes: List[Scene] = Field(default_factory=list)
    characters: List[Character] = Field(default_factory=list)
