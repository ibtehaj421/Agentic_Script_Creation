"""LLM-powered tools: story generation, character design, edit-intent classification.

All use Groq (free tier, fast, JSON-mode-capable). The shared `_groq_chat`
helper enforces strict JSON responses.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from config import GROQ_API_KEY, GROQ_MODEL
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import KNOWN_INTENTS


class GroqError(RuntimeError):
    pass


def _groq_chat(system: str, user: str, temperature: float = 0.7) -> str:
    if not GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY not set; populate .env")
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


class StoryGeneratorTool(BaseTool):
    spec = ToolSpec(
        name="generate_story",
        description="Expand a user prompt into a title+logline+scene-by-scene screenplay JSON.",
        category="llm",
        schema={"prompt": "str", "num_scenes": "int", "style": "str"},
    )

    def run(self, prompt: str, num_scenes: int = 3, style: str = "cinematic") -> dict[str, Any]:
        system = (
            "You are a senior screenwriter writing a short film. Output STRICT JSON only. "
            "Schema: {\"title\":str,\"logline\":str,"
            "\"scenes\":[{\"scene_id\":int,\"location\":str,\"action\":str,"
            "\"mood\":str,\"characters\":[str],"
            "\"dialogue\":[{\"speaker\":str,\"line\":str,\"visual_cue\":str,\"emotion\":str}]}]}\n\n"
            "CRITICAL: `line` is the actual SPOKEN words the character says out loud — "
            "quoted speech, in-character, addressed to another character or themselves. "
            "It is NEVER a stage direction, scene description, or visual description. "
            "Visual descriptions go in `visual_cue`, NOT in `line`.\n\n"
            "BAD `line` examples (these are descriptions, not speech): "
            "\"Rain pours down\", \"Shadows hide faces\", \"Figure emerges\", \"Eyes lock intensely\". "
            "GOOD `line` examples (real speech): "
            "\"You said no one would follow you here.\", "
            "\"I shouldn't be here. They'll kill me if they find out.\", "
            "\"Show me the file. Now.\"\n"
        )
        user = (
            f"Write a coherent {num_scenes}-scene {style} short film for this premise:\n"
            f"{prompt}\n\n"
            "Rules:\n"
            "(1) 2-4 recurring characters total.\n"
            "(2) Each scene has 2-3 dialogue lines that ADVANCE THE STORY — characters reveal "
            "information, react, push or pull at each other. Not weather reports.\n"
            "(3) Every `line` is between 8 and 25 words. Sounds like a person ACTUALLY talking — "
            "use contractions, false starts, trailing thoughts, interjections. "
            "Examples of what makes a line sound human: \"I... I don't know if I should be telling you this.\" / "
            "\"Look, just — just sit down, alright?\" / \"He said... he said it was over. But it wasn't, was it.\" "
            "Use commas, em-dashes, ellipses to mark natural pauses. Avoid expository over-explaining.\n"
            "(4) `visual_cue` (separate field) is a vivid one-clause description of what the camera "
            "sees while the line is spoken. `emotion` is a single word.\n"
            "(5) `mood` is one of: tense, urgent, happy, sad, mysterious, action, reflective, "
            "determined, neutral.\n"
        )
        # NOTE: temperature=0.0 is set for the demo recording so the same
        # prompt produces (close to) the same story output, which lets the
        # asset cache hit on visual_cue / dialogue keys. After recording,
        # bump back to 0.8 for varied creative output across runs.
        raw = _groq_chat(system, user, temperature=0.0)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"title": "Untitled", "logline": prompt[:120], "scenes": [], "_error": "llm_parse_failed", "_raw": raw}


class CharacterDesignerTool(BaseTool):
    spec = ToolSpec(
        name="design_characters",
        description="Extract character identity records (appearance, traits, voice_style) from a scene manifest.",
        category="llm",
        schema={"scene_manifest": "dict"},
    )

    def run(self, scene_manifest: dict) -> dict[str, Any]:
        system = (
            "You are a character designer. Output STRICT JSON only. "
            "Schema: {\"characters\":[{\"name\":str,\"role\":str,"
            "\"personality_traits\":[str],\"appearance\":str,"
            "\"voice_style\":str,\"gender\":str,\"reference_style\":str}]}"
        )
        user = (
            "Given this scene manifest, produce a consistent identity record for every named character. "
            "`appearance` must be a single vivid sentence specific enough to drive a diffusion model (face, hair, clothing, era/setting). "
            "`gender` must be exactly one of: \"male\", \"female\", \"neutral\" — "
            "infer from the character's name, appearance, and any contextual cues. "
            "Use \"neutral\" only when the character is genuinely androgynous or non-human; "
            "otherwise pick \"male\" or \"female\" so the TTS picks an appropriate voice. "
            "`voice_style` should be one of: deep, warm, crisp, raspy, whispered, commanding, youthful, elderly, sultry, monotone. "
            "`reference_style` should be one of: cinematic, anime, noir, cyberpunk, photorealistic, watercolor.\n\n"
            + json.dumps(scene_manifest)
        )
        # See temperature=0.0 note in StoryGeneratorTool — same demo-recording
        # rationale (deterministic-ish character roster → portrait cache hit).
        raw = _groq_chat(system, user, temperature=0.0)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"characters": []}


class EditIntentTool(BaseTool):
    """Classifies a free-text edit query into the Phase 5 EditIntent schema."""

    spec = ToolSpec(
        name="classify_edit_intent",
        description="Classify a user's natural-language edit command into a structured EditIntent.",
        category="llm",
        schema={"query": "str", "context": "dict"},
    )

    def run(self, query: str, context: dict | None = None) -> dict[str, Any]:
        known = ", ".join(KNOWN_INTENTS)
        ctx_json = json.dumps(context or {})[:2000]
        system = (
            "You classify editing commands for a video generation pipeline. "
            "Output STRICT JSON only with this schema: "
            "{\"intent\":str,\"target\":one_of(\"audio\",\"video_frame\",\"video\",\"script\"),"
            "\"scope\":str,\"parameters\":object,\"confidence\":float}. "
            f"`intent` should be one of: {known} (or a new snake_case verb if none fits). "
            "`scope` formats: \"character:<Name>\", \"scene:<id>\", \"global\". "
            "`parameters` should be a concrete dict.\n\n"
            "Routing rules: voice/music/dialogue audio => audio; recolor/relight/character-look per frame => video_frame; "
            "subtitles/transitions/speed/compositing => video; story/plot/dialogue-content changes => script.\n\n"
            "GENERIC SCENE-VISUAL EDITS: any free-text directive about how a scene should LOOK "
            "(\"darker\", \"more orange\", \"warmer\", \"more saturated\", \"add buildings\", "
            "\"make it nighttime\", \"sepia tone\", \"add fog\") should map to "
            "intent=\"modify_scene_visual\", target=\"video_frame\". For these, populate `parameters` with: "
            "{\"prompt_suffix\": <string appended to the scene background prompt, e.g. 'darker, low-key lighting' or 'with city buildings in the distance'>, "
            "\"brightness_delta\": <float in [-0.4, 0.4], 0 = unchanged, negative = darker>, "
            "\"saturation_delta\": <float multiplier in [0.0, 2.0], 1.0 = unchanged, >1 = more saturated>, "
            "\"hue_shift\": <float degrees in [-180, 180], 0 = unchanged, +30 = warmer/orange, -30 = cooler/teal>}. "
            "Always include all four keys; use 0/1.0/0/empty-string for the dimensions the directive doesn't touch. "
            "EXAMPLES: "
            "\"make scene 1 darker\" → parameters={\"prompt_suffix\":\"darker, moody, low-key lighting\",\"brightness_delta\":-0.15,\"saturation_delta\":0.9,\"hue_shift\":0}. "
            "\"more orange\" → parameters={\"prompt_suffix\":\"warm orange tones, sunset palette\",\"brightness_delta\":0,\"saturation_delta\":1.15,\"hue_shift\":25}. "
            "\"add buildings to scene 2\" → parameters={\"prompt_suffix\":\"with city skyline buildings in the background\",\"brightness_delta\":0,\"saturation_delta\":1.0,\"hue_shift\":0}.\n\n"
            "Stick with legacy intents (make_scene_darker, make_scene_brighter, apply_style_filter) ONLY if the query is a near-exact match to those phrasings; otherwise prefer modify_scene_visual."
        )
        user = (
            f"User query: {query}\n\n"
            f"Current pipeline context (abridged): {ctx_json}\n\n"
            "Return the JSON object only."
        )
        raw = _groq_chat(system, user, temperature=0.2)
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            out = {
                "intent": "unknown",
                "target": "video",
                "scope": "global",
                "parameters": {},
                "confidence": 0.0,
            }
        out.setdefault("raw_query", query)
        return out
