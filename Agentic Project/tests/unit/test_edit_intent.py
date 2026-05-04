"""Phase 5 rubric: edit-intent classifier accuracy across ≥10 query types.

We test the keyword-based fallback (deterministic, offline) since the
LLM path requires network. The fallback rules must at minimum route each
canonical query to the right `target` bucket.
"""
from __future__ import annotations

import pytest

from agents.edit_agent.intent_classifier import classify_intent
from shared.schemas import EditTarget, PipelineState


@pytest.fixture
def empty_state():
    return PipelineState(job_id="t", prompt="p", num_scenes=1)


# (query, expected_target, expected_intent_substring)
CASES = [
    # audio
    ("change voice tone to whispered",         EditTarget.AUDIO,       "voice_tone"),
    ("change the voice character",             EditTarget.AUDIO,       "voice_character"),
    ("add background music",                   EditTarget.AUDIO,       "add_background_music"),
    ("remove the background music",            EditTarget.AUDIO,       "remove_background_music"),
    ("regenerate the audio for scene 2",       EditTarget.AUDIO,       "regenerate_scene_audio"),

    # video_frame
    ("make the scene darker",                  EditTarget.VIDEO_FRAME, "darker"),
    ("make the scene brighter",                EditTarget.VIDEO_FRAME, "brighter"),
    ("change the character design",            EditTarget.VIDEO_FRAME, "character_design"),
    ("regenerate scene image",                 EditTarget.VIDEO_FRAME, "regenerate_scene_image"),
    ("apply cyberpunk filter",                 EditTarget.VIDEO_FRAME, "style_filter"),

    # video
    ("remove the subtitle",                    EditTarget.VIDEO,       "remove_subtitle"),
    ("add the subtitles",                      EditTarget.VIDEO,       "add_subtitle"),
    ("speed up this scene",                    EditTarget.VIDEO,       "speed_up"),
    ("slow down this scene",                   EditTarget.VIDEO,       "slow_down"),
    ("change the transition to crossfade",     EditTarget.VIDEO,       "change_transition"),

    # script
    ("regenerate the script",                  EditTarget.SCRIPT,      "regenerate_script"),
    ("redo the story",                         EditTarget.SCRIPT,      "regenerate_script"),

    # Generic modify_scene_visual fallback for free-text directives
    ("make scene 1 more orange",               EditTarget.VIDEO_FRAME, "modify_scene_visual"),
    ("more saturated please",                  EditTarget.VIDEO_FRAME, "modify_scene_visual"),
    ("add buildings to scene 2",               EditTarget.VIDEO_FRAME, "modify_scene_visual"),
    ("make it nighttime",                      EditTarget.VIDEO_FRAME, "modify_scene_visual"),
]


@pytest.mark.parametrize("query,target,intent_sub", CASES)
def test_fallback_routing(monkeypatch, empty_state, query, target, intent_sub):
    # Force the LLM path to fail so we exercise the keyword fallback.
    # intent_classifier imported `execute` by name, so patch *there*.
    from agents.edit_agent import intent_classifier as ic
    def _boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(ic, "execute", _boom)

    intent = classify_intent(query, state=empty_state)
    assert intent.target == target, f"{query!r} → {intent.target} (expected {target})"
    assert intent_sub in intent.intent, f"{query!r} → intent={intent.intent}"


def _force_fallback(monkeypatch):
    from agents.edit_agent import intent_classifier as ic
    monkeypatch.setattr(ic, "execute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))


def test_scope_extraction_scene(empty_state, monkeypatch):
    _force_fallback(monkeypatch)
    intent = classify_intent("make scene 2 darker", state=empty_state)
    assert intent.scope == "scene:2"


def test_unknown_query_fallback(empty_state, monkeypatch):
    _force_fallback(monkeypatch)
    intent = classify_intent("xyzpqr gibberish", state=empty_state)
    assert intent.intent == "unknown"
    assert intent.target == EditTarget.VIDEO
