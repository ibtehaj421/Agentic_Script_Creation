"""LLM-backed edit-intent classification (with keyword-match fallback).

The classifier is the Phase 5 rubric item #1. It receives the free-text
query + current pipeline context and outputs a structured EditIntent.
We call Groq via the MCP tool layer; if the LLM is unreachable (offline
demo), we fall back to a deterministic keyword rule set so the demo never
blocks.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from mcp.tool_executor import execute
from shared.schemas import EditIntent, EditTarget, PipelineState


# Keyword → (intent, target, extractor) fallback. Extractor returns the
# `parameters` dict. Kept intentionally small + readable.
_KEYWORD_RULES: list[dict] = [
    # More-specific voice-character rule must come first so it out-matches
    # the generic "change the voice" pattern below.
    {
        "pattern": r"\b(change (the )?voice (actor|character)|swap voice|different voice|voice actor)\b",
        "intent": "change_voice_character", "target": EditTarget.AUDIO,
        "params": lambda q: {},
    },
    {
        "pattern": r"\b(voice tone|tone of voice|change (the )?voice(?! (actor|character))|make (them|him|her) (sound )?(whispered|calm|angry|sad|happy))\b",
        "intent": "change_voice_tone", "target": EditTarget.AUDIO,
        "params": lambda q: {"tone": _extract_tone(q)},
    },
    {
        "pattern": r"\b(add|play) (background )?music\b|\bBGM\b|\bsoundtrack\b",
        "intent": "add_background_music", "target": EditTarget.AUDIO,
        "params": lambda q: {"mood": _extract_mood(q) or "mysterious"},
    },
    {
        "pattern": r"\b(remove|mute|turn off) (the )?(background )?music\b",
        "intent": "remove_background_music", "target": EditTarget.AUDIO,
        "params": lambda q: {},
    },
    {
        "pattern": r"\b(regenerate|redo|remake) (the )?(audio|dialogue|voice(s)?)\b",
        "intent": "regenerate_scene_audio", "target": EditTarget.AUDIO,
        "params": lambda q: {},
    },
    {
        "pattern": r"\b(darker|make (the )?(scene|frame) darker|moody)\b",
        "intent": "make_scene_darker", "target": EditTarget.VIDEO_FRAME,
        "params": lambda q: {"brightness": 0.55, "contrast": 1.12},
    },
    {
        "pattern": r"\b(brighter|lighter|make (the )?(scene|frame) brighter)\b",
        "intent": "make_scene_brighter", "target": EditTarget.VIDEO_FRAME,
        "params": lambda q: {"brightness": 1.35, "contrast": 1.08},
    },
    # Generic colour/lighting/content directives — anything that asks to
    # modify the scene's *look*. Maps to the unified handler with structured
    # params extracted heuristically. The LLM path produces richer params;
    # this fallback covers offline classification.
    {
        "pattern": (
            r"\b(more (orange|red|warm|warmer|amber|sunset))\b|"
            r"\b(more (blue|cool|cooler|teal|cold))\b|"
            r"\b(more saturated|less saturated|desatur)\b|"
            r"\b(make (the )?(scene|background) (look )?(more |a bit |slightly )?\w+)\b|"
            r"\b(add (\w+\s){0,4}(buildings?|fog|rain|snow|stars?|clouds?|crowd|trees?))\b|"
            r"\b(make it (nighttime|night|dusk|dawn|daytime|day|stormy|sunny|foggy))\b"
        ),
        "intent": "modify_scene_visual", "target": EditTarget.VIDEO_FRAME,
        "params": lambda q: _modify_scene_params(q),
    },
    {
        "pattern": r"\b(change (the )?character('?s)? (design|look|appearance)|redesign (the )?character)\b",
        "intent": "change_character_design", "target": EditTarget.VIDEO_FRAME,
        "params": lambda q: {},
    },
    {
        "pattern": r"\b(regenerate|redo) (the )?(scene )?(image|background|visual|frame)\b",
        "intent": "regenerate_scene_image", "target": EditTarget.VIDEO_FRAME,
        "params": lambda q: {},
    },
    {
        "pattern": r"\b(remove|hide|turn off) (the )?(subtitle(s)?|caption(s)?)\b",
        "intent": "remove_subtitle", "target": EditTarget.VIDEO,
        "params": lambda q: {"burn": False},
    },
    {
        "pattern": r"\b(add|show|turn on) (the )?(subtitle(s)?|caption(s)?)\b",
        "intent": "add_subtitle", "target": EditTarget.VIDEO,
        "params": lambda q: {"burn": True},
    },
    {
        "pattern": r"\b(speed up|faster)\b",
        "intent": "speed_up_scene", "target": EditTarget.VIDEO,
        "params": lambda q: {"speed": 1.5},
    },
    {
        "pattern": r"\b(slow down|slower)\b",
        "intent": "slow_down_scene", "target": EditTarget.VIDEO,
        "params": lambda q: {"speed": 0.75},
    },
    {
        "pattern": r"\b(change (the )?transition|cross ?fade|cut transition|fade transition)\b",
        "intent": "change_transition", "target": EditTarget.VIDEO,
        "params": lambda q: {"transition": _extract_transition(q) or "fade"},
    },
    {
        "pattern": r"\b(regenerate|redo|rewrite) (the )?(script|story)\b",
        "intent": "regenerate_script", "target": EditTarget.SCRIPT,
        "params": lambda q: {},
    },
    {
        "pattern": r"\b(apply (the )?(sepia|noir|cyberpunk|warm|cold|vivid|vintage) (filter|look))\b|\b(sepia|noir|cyberpunk|vintage) (filter|look)\b",
        "intent": "apply_style_filter", "target": EditTarget.VIDEO_FRAME,
        "params": lambda q: {"filter": _extract_filter(q) or "cinematic"},
    },
]


def _extract_tone(q: str) -> str:
    for tone in ("whispered", "angry", "sad", "happy", "urgent", "tense", "determined", "reflective", "neutral", "surprised", "fearful"):
        if tone in q.lower():
            return tone
    return "neutral"


def _extract_mood(q: str) -> Optional[str]:
    for mood in ("tense", "urgent", "happy", "sad", "mysterious", "action", "reflective", "determined", "neutral"):
        if mood in q.lower():
            return mood
    return None


def _extract_transition(q: str) -> Optional[str]:
    q = q.lower()
    if "cross" in q and "fade" in q:
        return "xfade"
    if "fade" in q:
        return "fade"
    if "cut" in q:
        return "cut"
    return None


def _extract_filter(q: str) -> Optional[str]:
    for f in ("sepia", "noir", "cyberpunk", "warm", "cold", "vivid", "vintage"):
        if f in q.lower():
            return f
    return None


def _modify_scene_params(q: str) -> dict:
    """Heuristic extraction of structured colour/content params for a free-text
    "modify scene visual" directive. The LLM path produces better params; this
    is the offline-fallback heuristic so the demo never blocks."""
    ql = q.lower()
    suffix_bits: list[str] = []
    brightness, saturation, hue = 0.0, 1.0, 0.0

    # Lighting
    if any(w in ql for w in ("nighttime", "night", "dusk")):
        brightness -= 0.2
        suffix_bits.append("nighttime, low-key lighting")
    elif any(w in ql for w in ("daytime", "sunny", "bright daylight")):
        brightness += 0.15
        suffix_bits.append("bright daylight")

    # Colour temperature
    if any(w in ql for w in ("orange", "warm", "warmer", "amber", "sunset", "red")):
        hue += 25
        saturation += 0.15
        suffix_bits.append("warm orange tones")
    if any(w in ql for w in ("blue", "cool", "cooler", "teal", "cold")):
        hue -= 25
        saturation += 0.05
        suffix_bits.append("cool blue tones")

    # Saturation
    if "more saturated" in ql:
        saturation += 0.25
    if any(w in ql for w in ("less saturated", "desaturated", "desatur")):
        saturation -= 0.3

    # Atmospherics — content additions go through prompt_suffix only
    for w in ("fog", "rain", "snow", "stars", "clouds", "buildings", "city", "crowd", "trees"):
        if w in ql:
            suffix_bits.append(f"with {w}")

    return {
        "prompt_suffix": ", ".join(suffix_bits),
        "brightness_delta": round(brightness, 3),
        "saturation_delta": round(saturation, 3),
        "hue_shift": round(hue, 1),
    }


def _extract_scope(query: str, state: Optional[PipelineState] = None) -> str:
    """Pick a scope from the query: "character:X" / "scene:N" / "global"."""
    q = query.lower()
    m = re.search(r"scene\s*(\d+)", q)
    if m:
        return f"scene:{int(m.group(1))}"
    if state:
        for c in state.story.characters:
            if c.name.lower() in q:
                return f"character:{c.name}"
    return "global"


def classify_intent(query: str, state: Optional[PipelineState] = None, job_id: Optional[str] = None) -> EditIntent:
    """Try LLM first; fall back to keyword rules on any error."""
    context = state.model_dump() if state else {}
    # Strip large fields to stay under token limits
    context.pop("log", None)
    context.pop("errors", None)

    try:
        raw = execute("classify_edit_intent", job_id=job_id, query=query, context=context)
        if isinstance(raw, dict) and raw.get("intent") and raw.get("target"):
            target = raw.get("target", "video")
            target_enum = EditTarget(target) if target in EditTarget._value2member_map_ else EditTarget.VIDEO
            return EditIntent(
                intent=raw.get("intent", "unknown"),
                target=target_enum,
                scope=raw.get("scope") or _extract_scope(query, state),
                parameters=raw.get("parameters") or {},
                confidence=float(raw.get("confidence") or 0.7),
                raw_query=query,
            )
    except Exception:
        pass

    # ── Fallback: keyword rules ───────────────────────────────────────
    for rule in _KEYWORD_RULES:
        if re.search(rule["pattern"], query, re.IGNORECASE):
            return EditIntent(
                intent=rule["intent"],
                target=rule["target"],
                scope=_extract_scope(query, state),
                parameters=rule["params"](query),
                confidence=0.6,
                raw_query=query,
            )
    # Default: treat unknown requests as full recomposition
    return EditIntent(
        intent="unknown",
        target=EditTarget.VIDEO,
        scope="global",
        parameters={},
        confidence=0.2,
        raw_query=query,
    )
