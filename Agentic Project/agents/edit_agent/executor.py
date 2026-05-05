"""Execute a plan step-by-step. Each step mutates the shared state."""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict

from agents.audio_agent import regenerate_scene_audio, run_audio_phase
from agents.story_agent import run_character_images, run_story_phase
from agents.video_agent import (
    adjust_scene_speed,
    apply_scene_style,
    burn_subtitles_toggle,
    recompose_final,
    regenerate_scene_background,
    run_video_phase,
)
from mcp.tool_executor import ToolExecutor
from shared.constants import VOICE_POOL
from shared.schemas import PipelineState
from shared.utils import emit


def execute_edit(
    plan: list[tuple[str, Dict[str, Any]]],
    state: PipelineState,
    job_id: str | None = None,
) -> PipelineState:
    job_id = job_id or state.job_id
    for step_name, kwargs in plan:
        handler = _HANDLERS.get(step_name)
        if not handler:
            emit(job_id, "edit", "unknown_step", {"step": step_name})
            continue
        emit(job_id, "edit", "step_start", {"step": step_name, "kwargs": kwargs})
        state = handler(state, job_id=job_id, **kwargs)
        emit(job_id, "edit", "step_done", {"step": step_name})
    return state


# ── Step handlers ────────────────────────────────────────────────────
def _h_story_rerun(
    state: PipelineState,
    job_id: str,
    parameters: dict | None = None,
    directive: str = "",
) -> PipelineState:
    # Keep the same prompt, regenerate the story. `directive` is the
    # user's raw edit query (e.g. "make Jack agree with Ava about the
    # aliens") — passed through to the LLM so the regen actually shapes
    # the new script around the user's intent.
    state.story.scenes = []
    state.story.characters = []
    state.audio = state.audio.__class__()
    state.video.scene_clips = {}
    state.video.final_mp4 = None
    return run_story_phase(state, job_id=job_id, directive=directive)


def _h_audio_rerun(state: PipelineState, job_id: str) -> PipelineState:
    return run_audio_phase(state, job_id=job_id)


def _h_video_rerun(state: PipelineState, job_id: str) -> PipelineState:
    state.video.scene_clips = {}
    return run_video_phase(state, job_id=job_id)


def _h_audio_regen(
    state: PipelineState, job_id: str, scene_id: int | None = None, overrides: dict | None = None,
) -> PipelineState:
    return regenerate_scene_audio(state, scene_id=scene_id, overrides=overrides, job_id=job_id)


def _h_video_rebuild_scene(state: PipelineState, job_id: str, scene_id: int | None = None) -> PipelineState:
    if scene_id is None:
        state.video.scene_clips = {}
        return run_video_phase(state, job_id=job_id)
    # Rebuild single scene + recompose
    clip = state.video.scene_clips.get(scene_id)
    if clip:
        clip.composed_path = None
        clip.raw_clip_path = None
    # Delegate full rebuild for that scene to the video agent
    from agents.video_agent.agent import _build_scene_clip, _render_final  # type: ignore
    ex = ToolExecutor(job_id=job_id)
    scene = next((s for s in state.story.scenes if s.scene_id == scene_id), None)
    if scene:
        _build_scene_clip(state, scene, ex, job_id)
        _render_final(state, ex, job_id)
    return state


def _h_video_regen_bg(
    state: PipelineState, job_id: str, scene_id: int | None = None, overrides: dict | None = None,
) -> PipelineState:
    if scene_id is None:
        # Apply to every scene
        for s in state.story.scenes:
            state = regenerate_scene_background(state, s.scene_id, overrides=overrides, job_id=job_id)
        return state
    return regenerate_scene_background(state, scene_id, overrides=overrides or {}, job_id=job_id)


def _h_video_apply_style(
    state: PipelineState, job_id: str, scene_id: int | None = None, filter_name: str = "vivid",
) -> PipelineState:
    if scene_id is None:
        for s in state.story.scenes:
            state = apply_scene_style(state, s.scene_id, filter_name, job_id=job_id)
        return state
    return apply_scene_style(state, scene_id, filter_name, job_id=job_id)


def _h_video_speed(
    state: PipelineState, job_id: str, scene_id: int | None = None, speed: float = 1.0,
) -> PipelineState:
    if scene_id is None:
        for s in state.story.scenes:
            state = adjust_scene_speed(state, s.scene_id, speed, job_id=job_id)
        return state
    return adjust_scene_speed(state, scene_id, speed, job_id=job_id)


def _h_video_recompose(state: PipelineState, job_id: str, transition: str | None = None) -> PipelineState:
    return recompose_final(state, transition=transition, job_id=job_id)


def _h_video_color_grade(
    state: PipelineState,
    job_id: str,
    scene_id: int | None = None,
    brightness: float = 0.0,
    saturation: float = 1.0,
    hue_shift: float = 0.0,
) -> PipelineState:
    """Run the new generic `apply_video_color_grade` tool against a scene
    MP4 (or every scene if scene_id is None) and re-render the final."""
    ex = ToolExecutor(job_id=job_id)
    targets = (
        list(state.video.scene_clips.values())
        if scene_id is None
        else [state.video.scene_clips.get(scene_id)]
    )
    for clip in targets:
        if not clip or not clip.composed_path:
            continue
        graded = ex.execute(
            "apply_video_color_grade",
            video_path=clip.composed_path,
            brightness=brightness,
            saturation=saturation,
            hue_shift=hue_shift,
        )
        clip.composed_path = graded
    # Recompose the final from the colour-graded scene paths
    return recompose_final(state, job_id=job_id)


def _h_video_burn_sub(state: PipelineState, job_id: str, burn: bool = True) -> PipelineState:
    return burn_subtitles_toggle(state, burn=burn, job_id=job_id)


def _h_story_set_mood(state: PipelineState, job_id: str, scene_id: int | None, mood: str) -> PipelineState:
    for s in state.story.scenes:
        if scene_id is None or s.scene_id == scene_id:
            s.mood = mood
    return state


def _h_story_change_voice(state: PipelineState, job_id: str, character: str) -> PipelineState:
    """Rotate a character's deterministic voice by nudging their voice_style."""
    styles_cycle = ["deep", "warm", "crisp", "raspy", "whispered", "commanding", "youthful", "sultry"]
    for c in state.story.characters:
        if c.name.lower() == character.lower():
            try:
                idx = styles_cycle.index(c.voice_style)
                c.voice_style = styles_cycle[(idx + 1) % len(styles_cycle)]
            except ValueError:
                # Current style is outside the cycle; seed by hash
                h = int(hashlib.md5(character.encode()).hexdigest(), 16)
                c.voice_style = styles_cycle[h % len(styles_cycle)]
    return state


def _h_story_update_appearance(
    state: PipelineState, job_id: str, character: str, tweak: dict | None = None,
) -> PipelineState:
    tweak = tweak or {}
    for c in state.story.characters:
        if c.name.lower() == character.lower():
            if tweak.get("appearance_suffix"):
                c.appearance = f"{c.appearance}, {tweak['appearance_suffix']}"
            if tweak.get("reference_style"):
                c.reference_style = tweak["reference_style"]
            c.image_path = None  # force regeneration
    return state


def _h_story_regen_char_image(state: PipelineState, job_id: str, character: str) -> PipelineState:
    for c in state.story.characters:
        if c.name.lower() == character.lower():
            c.image_path = None
    return run_character_images(state, job_id=job_id)


_HANDLERS: Dict[str, Callable[..., PipelineState]] = {
    "story.rerun": _h_story_rerun,
    "story.set_scene_mood": _h_story_set_mood,
    "story.change_character_voice": _h_story_change_voice,
    "story.update_character_appearance": _h_story_update_appearance,
    "story.regenerate_character_image": _h_story_regen_char_image,
    "audio.rerun": _h_audio_rerun,
    "audio.regenerate_scene_audio": _h_audio_regen,
    "video.rerun": _h_video_rerun,
    "video.rebuild_scene": _h_video_rebuild_scene,
    "video.regenerate_scene_background": _h_video_regen_bg,
    "video.apply_scene_style": _h_video_apply_style,
    "video.apply_scene_color_grade": _h_video_color_grade,
    "video.adjust_scene_speed": _h_video_speed,
    "video.recompose_final": _h_video_recompose,
    "video.burn_subtitles_toggle": _h_video_burn_sub,
}
