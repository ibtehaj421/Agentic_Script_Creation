"""Tiny helper that validates the LLM story output against the schema.

Implemented as a dedicated module so tests can exercise the normalisation
path without booting the Groq client."""
from __future__ import annotations

import re
from typing import Any

from shared.schemas import Character, DialogueTurn, Scene, StoryState


# LLMs sometimes embed stage directions in dialogue ("(whispers) I see it",
# "*sighs* fine", "[shouting] now!"). TTS reads them literally, so strip
# them before they hit the audio pipeline. The visible subtitle uses the
# same cleaned line, so on-screen text stays in sync with the spoken audio.
_STAGE_DIR_RE = re.compile(r"[\(\[\*][^\(\[\*\)\]]{1,40}[\)\]\*]")


def _strip_stage_directions(text: str) -> str:
    cleaned = _STAGE_DIR_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -—,;:")


def normalise_story(raw: dict[str, Any], prompt: str) -> StoryState:
    title = raw.get("title") or "Untitled"
    logline = raw.get("logline") or prompt[:160]
    scenes: list[Scene] = []
    for i, s in enumerate(raw.get("scenes", []), start=1):
        dialogue = [
            DialogueTurn(
                speaker=str(d.get("speaker", "Narrator")).strip() or "Narrator",
                line=_strip_stage_directions(str(d.get("line", ""))),
                visual_cue=str(d.get("visual_cue", "")).strip(),
                emotion=str(d.get("emotion", "neutral")).strip().lower() or "neutral",
            )
            for d in s.get("dialogue", [])
            if d.get("line") and _strip_stage_directions(str(d.get("line", "")))
        ]
        scenes.append(
            Scene(
                scene_id=int(s.get("scene_id") or i),
                location=str(s.get("location") or f"Scene {i}"),
                action=str(s.get("action") or ""),
                mood=str(s.get("mood") or "neutral").lower(),
                characters=[str(c) for c in s.get("characters", []) if c],
                dialogue=dialogue,
            )
        )
    return StoryState(title=title, logline=logline, prompt=prompt, scenes=scenes, characters=[])


_VALID_GENDERS = {"male", "female", "neutral"}


def normalise_characters(raw: dict[str, Any]) -> list[Character]:
    out: list[Character] = []
    for c in raw.get("characters", []):
        appearance = c.get("appearance", "")
        if isinstance(appearance, list):
            appearance = ", ".join(str(x) for x in appearance)
        gender = str(c.get("gender", "neutral")).strip().lower()
        if gender not in _VALID_GENDERS:
            gender = "neutral"
        out.append(
            Character(
                name=str(c.get("name", "")).strip() or "Unknown",
                role=str(c.get("role", "")),
                personality_traits=list(c.get("personality_traits", [])),
                appearance=appearance,
                voice_style=str(c.get("voice_style", "neutral")),
                gender=gender,
                reference_style=str(c.get("reference_style", "cinematic")),
            )
        )
    return out
