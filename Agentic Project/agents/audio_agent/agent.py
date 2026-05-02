"""Phase 2 — Audio Generation & Integration.

For each scene:
    * Per-dialogue-line TTS (edge-tts) — voice picked from character's voice_style
    * Concatenate lines into one scene dialogue wav
    * Generate mood-matched BGM track of matching duration
    * Mix dialogue over BGM with ducking → scene master wav
    * Fill timing manifest with start_ms/end_ms per line

The timing manifest is the contract Phase 3 consumes.
"""
from __future__ import annotations

from typing import Dict

from mcp.tool_executor import ToolExecutor
from shared.schemas import AudioSegment, PhaseStatus, PipelineState, TimingManifest
from shared.utils import emit, persist_state_manifest, probe_duration


def _voice_style_for(state: PipelineState, speaker: str) -> str:
    for c in state.story.characters:
        if c.name == speaker:
            return c.voice_style
    return "neutral"


def _gender_for(state: PipelineState, speaker: str) -> str:
    for c in state.story.characters:
        if c.name == speaker:
            return c.gender or "neutral"
    return "neutral"


def run_audio_phase(state: PipelineState, job_id: str | None = None) -> PipelineState:
    job_id = job_id or state.job_id
    state.phase_status["audio"] = PhaseStatus.RUNNING
    emit(job_id, "audio", "phase_start")

    ex = ToolExecutor(job_id=job_id)
    manifest = state.audio or TimingManifest()

    for scene in state.story.scenes:
        _synthesize_scene(state, scene, manifest, ex, job_id)

    state.audio = manifest
    state.phase_status["audio"] = PhaseStatus.DONE
    persist_state_manifest(state)
    emit(job_id, "audio", "phase_done", {"segments": len(manifest.segments)})
    return state


def regenerate_scene_audio(
    state: PipelineState,
    scene_id: int | None = None,
    overrides: dict | None = None,
    job_id: str | None = None,
) -> PipelineState:
    """Re-run TTS+BGM+mix for one scene (or all scenes if scene_id is None).

    `overrides` is passed to the TTS tool as kwargs (e.g. {"emotion":"whispered"}).
    """
    job_id = job_id or state.job_id
    ex = ToolExecutor(job_id=job_id)
    overrides = overrides or {}

    # Wipe affected segments so they regenerate cleanly
    manifest = state.audio or TimingManifest()
    if scene_id is None:
        manifest.segments = []
        manifest.scene_audio.clear()
        manifest.scene_durations_ms.clear()
        manifest.bgm_tracks.clear()
        target_scenes = state.story.scenes
    else:
        manifest.segments = [s for s in manifest.segments if s.scene_id != scene_id]
        manifest.scene_audio.pop(scene_id, None)
        manifest.scene_durations_ms.pop(scene_id, None)
        manifest.bgm_tracks.pop(scene_id, None)
        target_scenes = [s for s in state.story.scenes if s.scene_id == scene_id]

    for scene in target_scenes:
        _synthesize_scene(state, scene, manifest, ex, job_id, overrides=overrides)

    state.audio = manifest
    persist_state_manifest(state)
    return state


def _synthesize_scene(
    state: PipelineState,
    scene,  # Scene
    manifest: TimingManifest,
    ex: ToolExecutor,
    job_id: str,
    overrides: dict | None = None,
) -> None:
    overrides = overrides or {}
    scene_segments: list[AudioSegment] = []
    per_line_paths: list[str] = []

    for turn in scene.dialogue:
        voice_style = _voice_style_for(state, turn.speaker)
        gender = _gender_for(state, turn.speaker)
        emotion = overrides.get("emotion", turn.emotion)
        path = ex.execute(
            "tts_synthesize",
            speaker=turn.speaker,
            line=turn.line,
            emotion=emotion,
            voice_style=voice_style,
            gender=gender,
            override_voice=overrides.get("override_voice"),
        )
        per_line_paths.append(path)
        scene_segments.append(
            AudioSegment(
                scene_id=scene.scene_id,
                speaker=turn.speaker,
                line=turn.line,
                audio_file=path,
                emotion=emotion,
            )
        )

    # Concat dialogue per scene and fill timings
    dialogue_path = ex.execute(
        "merge_audio", op="concat", paths=per_line_paths,
        out_stem=f"scene_{scene.scene_id:02d}_dialogue",
    )

    # Set start/end per segment from real durations
    cursor_ms = 0
    for seg, path in zip(scene_segments, per_line_paths):
        dur_ms = int(probe_duration(path) * 1000)
        seg.start_ms = cursor_ms
        seg.end_ms = cursor_ms + dur_ms
        cursor_ms += dur_ms
    scene_duration_ms = cursor_ms
    scene.duration_s = round(scene_duration_ms / 1000.0, 3)

    # BGM track
    bgm_enabled = overrides.get("bgm", True)
    bgm_path = None
    if bgm_enabled:
        bgm_path = ex.execute(
            "generate_bgm",
            mood=scene.mood,
            duration_ms=max(scene_duration_ms, 2000),
            volume=overrides.get("bgm_volume"),
        )
        manifest.bgm_tracks[scene.scene_id] = bgm_path

    # Mix dialogue + BGM → scene master
    if bgm_path:
        scene_master = ex.execute(
            "merge_audio", op="mix_bgm",
            dialogue=dialogue_path, bgm=bgm_path,
            out_stem=f"scene_{scene.scene_id:02d}_master",
        )
    else:
        scene_master = dialogue_path

    manifest.scene_audio[scene.scene_id] = scene_master
    manifest.scene_durations_ms[scene.scene_id] = scene_duration_ms
    manifest.segments.extend(scene_segments)

    emit(
        job_id, "audio", "scene_ready",
        {"scene_id": scene.scene_id, "duration_ms": scene_duration_ms, "bgm": bgm_enabled},
    )
