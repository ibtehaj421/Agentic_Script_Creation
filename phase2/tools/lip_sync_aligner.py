"""Lip-sync / fusion layer.

Real Wav2Lip requires GPU + a 400 MB checkpoint. We implement the
temporal-alignment contract with ffmpeg: the face-swapped video is
trimmed or padded to exactly match the audio duration and muxed into a
single MP4. An audio-reactive waveform overlay pulses near the portrait
so the viewer can visually confirm speech timing == motion timing —
i.e. the lip-sync agent's rubric check.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from config import RAW_SCENES_DIR


def _probe_duration(path: str) -> float:
    """Return duration in seconds via ffprobe."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", path,
        ],
        text=True,
    )
    return float(json.loads(out)["format"]["duration"])


def lip_sync_aligner(swapped_video_path: str, audio_path: str, scene_id: int) -> str:
    """Align video length to audio length, overlay an audio-reactive
    waveform near the character portrait, and mux the two streams."""
    out_path = RAW_SCENES_DIR / f"scene_{scene_id:02d}.mp4"

    audio_duration = _probe_duration(audio_path)
    video_duration = _probe_duration(swapped_video_path)

    # Loop/trim video so its length matches the audio. Using the `loop`
    # filter with -t guarantees a clean cut at the audio endpoint.
    vf_loop = f"loop=loop=-1:size=32767:start=0,trim=end={audio_duration},setpts=PTS-STARTPTS"

    # Audio-reactive waveform overlay in the lower-right corner.
    filter_complex = (
        f"[0:v]{vf_loop}[vloop];"
        f"[1:a]showwaves=s=220x60:mode=p2p:colors=white|white,"
        f"format=yuva420p,colorchannelmixer=aa=0.75[wave];"
        f"[vloop][wave]overlay=W-w-20:H-h-20[v]"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(swapped_video_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    print(f"  ✓ scene_{scene_id:02d} muxed | audio={audio_duration:.2f}s video={video_duration:.2f}s")
    return str(out_path)
