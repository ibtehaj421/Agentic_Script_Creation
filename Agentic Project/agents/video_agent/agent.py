"""Phase 3 — Video Generation & Composition.

For each scene we now render one **sub-clip per dialogue line** using
that speaker's portrait as the main visual (Ken-Burns'd, cropped to
16:9, with the line's subtitle burned on). Sub-clips are concatenated
with hard cuts so the result reads as classic shot/reverse-shot. If a
speaker has no portrait we fall back to the scene's wide background
shot for that line so the pipeline never hard-fails.

Per scene:
    1. Generate (or reuse) the mood-matched 16:9 background (used as a
       fallback visual when a speaker has no portrait).
    2. For each dialogue line:
       a. Pick the speaker's portrait (or fall back to the BG).
       b. Ken-Burns it for the line's audio duration.
       c. Mux with that line's per-line audio.
       d. Burn the line's subtitle.
    3. Concat the per-line clips with hard cuts → scene MP4.

Then concat scene MP4s with xfade transitions → `final_output.mp4`.

Edit-agent hooks:
    regenerate_scene_background(state, scene_id, overrides)
    recompose_final(state, transition=...)  -- does not re-gen assets
    adjust_scene_speed(state, scene_id, speed)
    apply_scene_style(state, scene_id, filter)
    burn_subtitles_toggle(state, burn)
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, List, Optional

from config import SCENES_DIR, VIDEO_DIR
from mcp.tool_executor import ToolExecutor
from shared.schemas import PhaseStatus, PipelineState, SceneClip, VideoOutput
from shared.utils import emit, hash_short, job_dir as _job_dir, persist_state_manifest, probe_duration, video_encoder_args

from .subtitles import dialogue_segments_for


def run_video_phase(state: PipelineState, job_id: str | None = None) -> PipelineState:
    job_id = job_id or state.job_id
    state.phase_status["video"] = PhaseStatus.RUNNING
    emit(job_id, "video", "phase_start")

    ex = ToolExecutor(job_id=job_id)
    state.video = state.video or VideoOutput()

    for scene in state.story.scenes:
        _build_scene_clip(state, scene, ex, job_id)

    _render_final(state, ex, job_id)

    state.phase_status["video"] = PhaseStatus.DONE
    persist_state_manifest(state)
    emit(job_id, "video", "phase_done", {"final_mp4": state.video.final_mp4})
    return state


# ── Scene-level builder ────────────────────────────────────────────────
# Ken-Burns directions cycled so adjacent shots don't have identical
# motion (less monotonous on shot/reverse-shot).
_KB_DIRECTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left"]

# Brief location-establishing wide shot prepended to every scene. Long
# enough to register the setting and any content-level edits ("add
# buildings", "make it nighttime") that only affect the background;
# short enough not to drag.
_ESTABLISHING_DUR_S = 1.8


def _build_establishing_clip(scene, bg_path: str, ex: ToolExecutor, job_id: str) -> str | None:
    """Render a short wide Ken-Burns of the scene background with brief
    mood-BGM under it. Returns the composed MP4 path or None on failure.
    """
    try:
        bgm = ex.execute(
            "generate_bgm",
            mood=scene.mood,
            duration_ms=int(_ESTABLISHING_DUR_S * 1000),
        )
        kb = ex.execute(
            "ken_burns",
            image_path=bg_path,
            duration_s=_ESTABLISHING_DUR_S,
            direction="zoom_in",
        )
        # Use a unique scene_id (xx99) so the per-line clips (xx00..xx98)
        # never collide on filename in the job-scoped scenes dir.
        return ex.execute(
            "compose_scene",
            video_path=kb,
            audio_path=bgm,
            scene_id=scene.scene_id * 100 + 99,
        )
    except Exception as e:
        emit(job_id, "video", "establishing_failed", {"scene_id": scene.scene_id, "err": str(e)})
        return None


def _build_scene_clip(state: PipelineState, scene, ex: ToolExecutor, job_id: str) -> None:
    clip = state.video.scene_clips.get(scene.scene_id, SceneClip(scene_id=scene.scene_id))

    # Background — always generated so we have a fallback visual for any
    # line where the speaker has no portrait, and so the edit hooks
    # (make_scene_darker, etc.) still have something to operate on.
    if not clip.background_path or not Path(clip.background_path).exists():
        clip.background_path = ex.execute(
            "generate_scene_background",
            location=scene.location,
            visual_cue=" ".join(t.visual_cue for t in scene.dialogue),
            action=scene.action,
            mood=scene.mood,
            style=state.style,
        )
        emit(job_id, "video", "background_ready", {"scene_id": scene.scene_id, "path": clip.background_path})

    # Build one composed sub-clip per dialogue line, using that speaker's
    # portrait as the main visual.
    line_clips: List[str] = []
    total_duration = 0.0

    # Establishing shot: brief wide Ken-Burns of the scene background.
    # Renders the *current* background image, so any content-level edit
    # ("add buildings", "make it nighttime") is visible at the start of
    # the scene even though dialogue close-ups don't show the BG.
    if clip.background_path:
        establishing = _build_establishing_clip(scene, clip.background_path, ex, job_id)
        if establishing:
            line_clips.append(establishing)
            total_duration += _ESTABLISHING_DUR_S

    for line_idx, line in enumerate(scene.dialogue):
        seg_path = _audio_path_for_line(state, scene.scene_id, line_idx, line)
        if not seg_path:
            continue
        line_dur = max(probe_duration(seg_path), 0.5)

        speaker_portrait = _portrait_for(state, line.speaker)
        visual = speaker_portrait or clip.background_path

        kb_clip = ex.execute(
            "ken_burns",
            image_path=visual,
            duration_s=line_dur,
            direction=_KB_DIRECTIONS[(scene.scene_id + line_idx) % len(_KB_DIRECTIONS)],
        )

        line_mp4 = ex.execute(
            "compose_scene",
            video_path=kb_clip,
            audio_path=seg_path,
            scene_id=scene.scene_id * 100 + line_idx,  # unique cache key per line
            job_id=job_id,
        )

        if state.video.subtitles_burned:
            sub_segment = {
                "speaker": line.speaker,
                "text": line.line,
                "start_s": 0.0,
                "end_s": line_dur,
            }
            line_mp4 = ex.execute("burn_subtitles", video_path=line_mp4, segments=[sub_segment])

        line_clips.append(line_mp4)
        total_duration += line_dur

    if not line_clips:
        # Fallback: empty/missing dialogue → render the BG over scene audio.
        scene_audio = state.audio.scene_audio.get(scene.scene_id)
        duration = (
            max(probe_duration(scene_audio), 2.5) if scene_audio
            else (scene.duration_s if scene.duration_s > 0 else 6.0)
        )
        kb = ex.execute(
            "ken_burns",
            image_path=clip.background_path,
            duration_s=duration,
            direction=_KB_DIRECTIONS[(scene.scene_id - 1) % len(_KB_DIRECTIONS)],
        )
        composed = ex.execute(
            "compose_scene",
            video_path=kb,
            audio_path=scene_audio or _silence_wav(duration),
            scene_id=scene.scene_id,
            job_id=job_id,
        )
        clip.composed_path = composed
        clip.duration_s = duration
        state.video.scene_clips[scene.scene_id] = clip
        emit(job_id, "video", "scene_composed", {"scene_id": scene.scene_id, "path": composed})
        return

    # Concat per-line sub-clips into the scene MP4 (hard cuts). Job-scoped
    # output directory so two jobs' scene MP4s never overwrite each other.
    scenes_out = SCENES_DIR / job_id
    scenes_out.mkdir(parents=True, exist_ok=True)
    scene_path = scenes_out / f"scene_{scene.scene_id:02d}.mp4"
    _concat_cut(line_clips, scene_path, job_id=job_id)

    clip.composed_path = str(scene_path)
    clip.duration_s = total_duration
    state.video.scene_clips[scene.scene_id] = clip

    emit(
        job_id, "video", "scene_composed",
        {"scene_id": scene.scene_id, "path": str(scene_path), "lines": len(line_clips)},
    )


def _concat_cut(clip_paths: List[str], out_path: Path, job_id: str | None = None) -> None:
    """Concat MP4s with hard cuts. All clips must share codec/resolution/SAR."""
    list_file = _job_dir(VIDEO_DIR, job_id) / f"_concat_lines_{hash_short('|'.join(clip_paths))}.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in clip_paths))
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            *video_encoder_args(bitrate="6M"),
            "-c:a", "aac", "-b:a", "160k",
            str(out_path),
        ],
        check=True,
    )


# ── Final compositor ──────────────────────────────────────────────────
def _render_final(state: PipelineState, ex: ToolExecutor, job_id: str) -> str:
    scenes = sorted(state.video.scene_clips.values(), key=lambda c: c.scene_id)
    paths: List[str] = [c.composed_path for c in scenes if c.composed_path]
    if not paths:
        raise RuntimeError("no scene clips to compose final")

    final = ex.execute(
        "compose_final",
        scene_paths=paths,
        out_name=f"final_{state.job_id}.mp4",
        transition=state.video.transitions,
    )
    state.video.final_mp4 = final
    emit(job_id, "video", "final_ready", {"path": final})
    return final


# ── Edit hooks ────────────────────────────────────────────────────────
def regenerate_scene_background(state: PipelineState, scene_id: int, overrides: dict[str, Any] | None = None, job_id: str | None = None) -> PipelineState:
    """Edit intent `make_scene_darker` / `change_character_design` entry point."""
    job_id = job_id or state.job_id
    ex = ToolExecutor(job_id=job_id)
    overrides = overrides or {}

    scene = next((s for s in state.story.scenes if s.scene_id == scene_id), None)
    if not scene:
        return state

    clip = state.video.scene_clips.get(scene_id, SceneClip(scene_id=scene_id))
    # Augment visual cue with user mood tokens (e.g. "darker", "brighter")
    extra = overrides.get("prompt_suffix", "")
    visual_cue = " ".join(t.visual_cue for t in scene.dialogue) + " " + extra

    bg = ex.execute(
        "generate_scene_background",
        location=scene.location,
        visual_cue=visual_cue,
        action=scene.action,
        mood=overrides.get("mood", scene.mood),
        style=overrides.get("style", state.style),
    )

    # Optional: apply colour adjustments on top (for "darker"/"brighter")
    if "brightness" in overrides or "contrast" in overrides:
        bg = ex.execute(
            "adjust_image_color",
            src_path=bg,
            brightness=overrides.get("brightness", 1.0),
            contrast=overrides.get("contrast", 1.0),
            saturation=overrides.get("saturation", 1.0),
        )
    if overrides.get("filter"):
        bg = ex.execute("apply_style_filter", src_path=bg, filter=overrides["filter"])

    clip.background_path = bg
    # Invalidate downstream products so rebuild regenerates
    clip.raw_clip_path = None
    clip.composed_path = None
    state.video.scene_clips[scene_id] = clip
    _build_scene_clip(state, scene, ex, job_id)
    _render_final(state, ex, job_id)
    persist_state_manifest(state)
    return state


def recompose_final(state: PipelineState, transition: str | None = None, job_id: str | None = None) -> PipelineState:
    job_id = job_id or state.job_id
    if transition:
        state.video.transitions = transition
    ex = ToolExecutor(job_id=job_id)
    _render_final(state, ex, job_id)
    persist_state_manifest(state)
    return state


def adjust_scene_speed(state: PipelineState, scene_id: int, speed: float, job_id: str | None = None) -> PipelineState:
    job_id = job_id or state.job_id
    ex = ToolExecutor(job_id=job_id)
    clip = state.video.scene_clips.get(scene_id)
    if not clip or not clip.composed_path:
        return state
    new_path = ex.execute("adjust_speed", video_path=clip.composed_path, speed=speed)
    clip.composed_path = new_path
    state.video.scene_clips[scene_id] = clip
    _render_final(state, ex, job_id)
    persist_state_manifest(state)
    return state


def apply_scene_style(state: PipelineState, scene_id: int, filter_name: str, job_id: str | None = None) -> PipelineState:
    job_id = job_id or state.job_id
    ex = ToolExecutor(job_id=job_id)
    clip = state.video.scene_clips.get(scene_id)
    if not clip or not clip.background_path:
        return state
    styled_bg = ex.execute("apply_style_filter", src_path=clip.background_path, filter=filter_name)
    clip.background_path = styled_bg
    clip.raw_clip_path = None
    clip.composed_path = None
    state.video.scene_clips[scene_id] = clip
    scene = next(s for s in state.story.scenes if s.scene_id == scene_id)
    _build_scene_clip(state, scene, ex, job_id)
    _render_final(state, ex, job_id)
    persist_state_manifest(state)
    return state


def burn_subtitles_toggle(state: PipelineState, burn: bool, job_id: str | None = None) -> PipelineState:
    """Rebuild every scene clip and the final video with/without subtitles."""
    job_id = job_id or state.job_id
    state.video.subtitles_burned = burn
    ex = ToolExecutor(job_id=job_id)
    for scene in state.story.scenes:
        clip = state.video.scene_clips.get(scene.scene_id)
        if clip:
            clip.composed_path = None
        _build_scene_clip(state, scene, ex, job_id)
    _render_final(state, ex, job_id)
    persist_state_manifest(state)
    return state


# ── Helpers ───────────────────────────────────────────────────────────
def _primary_portrait(state: PipelineState, scene) -> str | None:
    for name in scene.characters:
        for c in state.story.characters:
            if c.name == name and c.image_path:
                return c.image_path
    return None


def _portrait_for(state: PipelineState, speaker: str) -> Optional[str]:
    """Return the portrait path for `speaker` if one exists."""
    for c in state.story.characters:
        if c.name == speaker and c.image_path and Path(c.image_path).exists():
            return c.image_path
    return None


def _audio_path_for_line(state: PipelineState, scene_id: int, line_idx: int, line) -> Optional[str]:
    """Find the per-line wav. Match by (scene_id, speaker, line text); fall
    back to nth-segment-in-scene if exact text match fails."""
    in_scene = [s for s in state.audio.segments if s.scene_id == scene_id]
    # Exact match on (speaker, line)
    for s in in_scene:
        if s.speaker == line.speaker and s.line.strip() == line.line.strip():
            return s.audio_file
    # Positional fallback (covers subtle whitespace/punctuation drift)
    if line_idx < len(in_scene):
        return in_scene[line_idx].audio_file
    return None


def _silence_wav(duration_s: float) -> str:
    """Deterministic silent wav for scenes without audio (edge case)."""
    import subprocess

    out = VIDEO_DIR / f"_silence_{int(duration_s * 1000)}.wav"
    if out.exists():
        return str(out)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
            "-t", f"{duration_s:.3f}",
            str(out),
        ],
        check=True,
    )
    return str(out)
