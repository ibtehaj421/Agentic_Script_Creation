"""Maps an EditIntent to a concrete execution plan.

A plan is a list of (callable_name, kwargs) the executor walks top-to-bottom.
Keeping this layer separate lets us test "intent X plans to action Y"
without touching the pipeline.
"""
from __future__ import annotations

from typing import Any, List, Tuple

from shared.schemas import EditIntent, EditTarget, PipelineState


def plan_execution(intent: EditIntent, state: PipelineState) -> List[Tuple[str, dict[str, Any]]]:
    plan: List[Tuple[str, dict]] = []
    scope = intent.scope or "global"
    scene_id = _scene_from_scope(scope)
    character = _character_from_scope(scope)

    if intent.target == EditTarget.AUDIO:
        if intent.intent == "remove_background_music":
            overrides = {"bgm": False}
            plan.append(("audio.regenerate_scene_audio", {"scene_id": scene_id, "overrides": overrides}))
        elif intent.intent == "add_background_music":
            mood = intent.parameters.get("mood")
            if scene_id is not None and mood:
                # Change scene mood so BGM follows
                plan.append(("story.set_scene_mood", {"scene_id": scene_id, "mood": mood}))
            plan.append(("audio.regenerate_scene_audio", {"scene_id": scene_id, "overrides": {"bgm": True}}))
        elif intent.intent == "change_voice_tone":
            tone = intent.parameters.get("tone", "neutral")
            plan.append(("audio.regenerate_scene_audio", {"scene_id": scene_id, "overrides": {"emotion": tone}}))
        elif intent.intent == "change_voice_character":
            # If user pointed at a character, shuffle their voice_style
            if character:
                plan.append(("story.change_character_voice", {"character": character}))
            plan.append(("audio.regenerate_scene_audio", {"scene_id": scene_id, "overrides": {}}))
        else:  # regenerate_scene_audio or unknown audio edit
            plan.append(("audio.regenerate_scene_audio", {"scene_id": scene_id, "overrides": intent.parameters}))
        # Always recompose video so the new audio lands in the final file
        plan.append(("video.rebuild_scene", {"scene_id": scene_id}))

    elif intent.target == EditTarget.VIDEO_FRAME:
        if intent.intent in ("modify_scene_visual", "make_scene_darker", "make_scene_brighter"):
            # Unified handler. Legacy darker/brighter aliases fill in default
            # color deltas + suffix when the LLM didn't supply them.
            p = dict(intent.parameters)
            if intent.intent == "make_scene_darker":
                p.setdefault("prompt_suffix", "darker, moody, low-key lighting")
                p.setdefault("brightness_delta", -0.15)
                p.setdefault("saturation_delta", 0.9)
            elif intent.intent == "make_scene_brighter":
                p.setdefault("prompt_suffix", "brighter, high-key lighting")
                p.setdefault("brightness_delta", 0.15)
                p.setdefault("saturation_delta", 1.05)

            suffix = p.get("prompt_suffix", "")
            if suffix:
                plan.append((
                    "video.regenerate_scene_background",
                    {"scene_id": scene_id, "overrides": {"prompt_suffix": suffix}},
                ))
            color = {
                "brightness": float(p.get("brightness_delta", 0.0) or 0.0),
                "saturation": float(p.get("saturation_delta", 1.0) or 1.0),
                "hue_shift": float(p.get("hue_shift", 0.0) or 0.0),
            }
            non_identity = (
                abs(color["brightness"]) > 1e-3
                or abs(color["saturation"] - 1.0) > 1e-3
                or abs(color["hue_shift"]) > 0.5
            )
            if non_identity:
                plan.append((
                    "video.apply_scene_color_grade",
                    {"scene_id": scene_id, **color},
                ))
        elif intent.intent == "apply_style_filter":
            plan.append(("video.apply_scene_style", {"scene_id": scene_id, "filter_name": intent.parameters.get("filter", "vivid")}))
        elif intent.intent == "change_character_design":
            if character:
                plan.append(("story.update_character_appearance", {"character": character, "tweak": intent.parameters}))
                plan.append(("story.regenerate_character_image", {"character": character}))
            plan.append(("video.regenerate_scene_background", {"scene_id": scene_id, "overrides": intent.parameters}))
        else:  # regenerate_scene_image / unknown frame edit
            plan.append(("video.regenerate_scene_background", {"scene_id": scene_id, "overrides": intent.parameters}))

    elif intent.target == EditTarget.VIDEO:
        if intent.intent in ("speed_up_scene", "slow_down_scene"):
            # LLM sometimes returns `speed_multiplier`, `factor`, or `rate` — normalise.
            p = intent.parameters
            speed = (
                p.get("speed")
                or p.get("speed_multiplier")
                or p.get("factor")
                or p.get("rate")
                or (1.5 if intent.intent == "speed_up_scene" else 0.75)
            )
            plan.append(("video.adjust_scene_speed", {"scene_id": scene_id, "speed": float(speed)}))
        elif intent.intent == "change_transition":
            plan.append(("video.recompose_final", {"transition": intent.parameters.get("transition", "fade")}))
        elif intent.intent in ("remove_subtitle", "add_subtitle"):
            plan.append(("video.burn_subtitles_toggle", {"burn": bool(intent.parameters.get("burn"))}))
        else:
            plan.append(("video.recompose_final", {}))

    elif intent.target == EditTarget.SCRIPT:
        # Pass the raw user query as a directive so the LLM actually
        # incorporates the requested change (e.g. "make Jack agree with
        # Ava about the aliens") instead of regenerating the same story
        # from the original prompt and ignoring the edit intent entirely.
        plan.append((
            "story.rerun",
            {"parameters": intent.parameters, "directive": intent.raw_query or ""},
        ))
        plan.append(("audio.rerun", {}))
        plan.append(("video.rerun", {}))

    return plan


def _scene_from_scope(scope: str) -> int | None:
    if scope.startswith("scene:"):
        try:
            return int(scope.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


def _character_from_scope(scope: str) -> str | None:
    if scope.startswith("character:"):
        return scope.split(":", 1)[1] or None
    return None
