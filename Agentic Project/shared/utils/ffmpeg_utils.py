"""Thin wrappers around ffmpeg / ffprobe so call sites stay readable."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List


class FFmpegError(RuntimeError):
    pass


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise FFmpegError(f"{binary} not found on PATH; please install ffmpeg.")
    return path


def run_ffmpeg(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    """Run ffmpeg with sensible defaults. Raises FFmpegError on non-zero exit."""
    cmd = [_require("ffmpeg"), "-y", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=capture, text=capture)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() if capture else "(see terminal)"
        raise FFmpegError(f"ffmpeg failed ({result.returncode}): {stderr}")
    return result


def probe_duration(path: str | Path) -> float:
    """Return duration in seconds via ffprobe."""
    _require("ffprobe")
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        text=True,
    )
    return float(json.loads(out)["format"]["duration"])


_ENCODER_CACHE: dict[str, bool] = {}


def _encoder_available(name: str) -> bool:
    if name in _ENCODER_CACHE:
        return _ENCODER_CACHE[name]
    try:
        out = subprocess.check_output(
            [_require("ffmpeg"), "-hide_banner", "-encoders"],
            text=True, stderr=subprocess.STDOUT,
        )
        _ENCODER_CACHE[name] = name in out
    except Exception:
        _ENCODER_CACHE[name] = False
    return _ENCODER_CACHE[name]


def video_encoder_args(bitrate: str = "5M") -> List[str]:
    """Pick the best available H.264 encoder.

    On Apple Silicon `h264_videotoolbox` is ~6-8× faster than libx264 at
    comparable quality. Falls back to libx264 veryfast otherwise.

    NOTE on pixel format: macOS `h264_videotoolbox` ignores `-pix_fmt
    yuv420p` and outputs `yuvj420p` (full-range, JPEG-style) by default,
    which Firefox refuses to play in HTML5 <video>. We force the
    output to `yuv420p` + `-color_range tv` (limited range, 16-235) so
    every browser handles the file correctly. The `-vf format=yuv420p`
    is the actual hammer that converts the frames; `-pix_fmt yuv420p`
    alone is silently ignored by videotoolbox on some macOS builds.
    """
    from shared.constants import VIDEO_ENCODER, VIDEO_ENCODER_FALLBACK
    if _encoder_available(VIDEO_ENCODER):
        return [
            "-c:v", VIDEO_ENCODER,
            "-b:v", bitrate,
            "-allow_sw", "1",       # software fallback if HW path fails
            "-pix_fmt", "yuv420p",
            "-color_range", "tv",   # limited (broadcast) range
        ]
    return [
        "-c:v", VIDEO_ENCODER_FALLBACK,
        "-preset", "veryfast",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-color_range", "tv",
    ]
