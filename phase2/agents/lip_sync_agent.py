"""Lip Sync Agent (Fusion Layer).

Runs once as a barrier after both the audio and video branches finish.
For every scene that has both a face-swapped video and at least one
dialogue wav, it:
    1. concatenates the per-speaker WAVs in dialogue order,
    2. calls lip_sync_aligner to mux video + audio and overlay a
       waveform, producing the final `outputs/raw_scenes/scene_NN.mp4`.

The node is idempotent: scenes already committed to the final
checkpoint are skipped, so repeated invocations from LangGraph's
super-step scheduler are safe.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from config import AUDIO_OUT_DIR
from tools.commit_memory import checkpoint_exists, commit_memory, load_checkpoint
from tools.lip_sync_aligner import lip_sync_aligner


def merge_audio_tracks(audio_paths: list[str], scene_id: int) -> str:
    merged_path = Path(AUDIO_OUT_DIR) / f"scene_{scene_id}_merged.wav"

    if len(audio_paths) == 1:
        shutil.copy(audio_paths[0], merged_path)
        return str(merged_path)

    # Atomic: render to a temp file, then rename over the target.
    with tempfile.NamedTemporaryFile(
        suffix=".wav", dir=AUDIO_OUT_DIR, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    inputs: list[str] = []
    for p in audio_paths:
        inputs.extend(["-i", p])
    filter_str = (
        "".join(f"[{i}:a]" for i in range(len(audio_paths)))
        + f"concat=n={len(audio_paths)}:v=0:a=1[out]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[out]",
        str(tmp_path),
    ]
    print(f"🔊 Merging dialogue audio for scene {scene_id}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg merge failed: {e.stderr.decode()}") from e

    os.replace(tmp_path, merged_path)
    return str(merged_path)


def lip_sync_node(state: dict) -> dict:
    """Barrier that finalises every scene with both audio and video ready."""
    outputs = dict(state.get("final_outputs", {}))
    audio_outputs = state.get("audio_outputs", {}) or {}
    face_swapped = state.get("face_swapped_outputs", {}) or {}

    for scene in state.get("task_graph", []):
        scene_id = scene["scene_id"]
        key = f"scene_{scene_id}"
        if key in outputs:
            continue
        if checkpoint_exists(f"final_{scene_id}"):
            outputs[key] = load_checkpoint(f"final_{scene_id}")
            continue

        swapped_video = face_swapped.get(key)
        if not swapped_video:
            continue

        audio_paths = []
        for turn in scene["dialogue"]:
            speaker_key = f"scene_{scene_id}_{turn['speaker'].replace(' ', '_')}"
            if speaker_key in audio_outputs:
                audio_paths.append(audio_outputs[speaker_key])
        if not audio_paths:
            continue

        merged_audio = merge_audio_tracks(audio_paths, scene_id)
        final_mp4 = lip_sync_aligner(swapped_video, merged_audio, scene_id)
        commit_memory(final_mp4, checkpoint_id=f"final_{scene_id}")
        outputs[key] = final_mp4

    return {"final_outputs": outputs}
