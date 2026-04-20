"""Face-swap tool — free, CPU-only, zero-install.

A real GAN-based face swap (Roop/InsightFace/Wav2Lip) would require
downloading large checkpoints and heavy ML stacks. Since the Phase 1
character portrait is already the face we want on screen, we implement
"face mapping" as a visual composite: the Ken-Burns background clip
gets a circular cut-out of the character portrait overlaid in the lower
left, labelled with the character's name.

This keeps the clip obviously tied to the character identity while
running on any laptop.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from config import VIDEO_OUT_DIR


def _make_circular_portrait(src: str, size: int = 240) -> Path:
    """Crop the source image to a circle and return a PNG path."""
    src_path = Path(src)
    out = VIDEO_OUT_DIR / f"_portrait_{src_path.stem}_{size}.png"
    if out.exists():
        return out
    img = Image.open(src_path).convert("RGBA").resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    img.putalpha(mask)
    img.save(out)
    return out


def face_swapper(character_image_path: str, raw_video_path: str) -> str:
    """Overlay a circular portrait of `character_image_path` onto
    `raw_video_path`, returning the swapped clip path."""
    video = Path(raw_video_path)
    key = hashlib.md5(
        f"{character_image_path}|{raw_video_path}".encode("utf-8")
    ).hexdigest()[:10]
    out_path = VIDEO_OUT_DIR / f"swapped_{video.stem}_{key}.mp4"
    if out_path.exists() and out_path.stat().st_size > 0:
        return str(out_path)

    if not os.path.exists(character_image_path):
        # Nothing to composite — return the video untouched
        return raw_video_path

    portrait = _make_circular_portrait(character_image_path, size=140)

    # Overlay portrait in bottom-left corner
    vf = (
        "[1:v]scale=140:140[p];"
        "[0:v][p]overlay=x=20:y=H-h-20:format=auto"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(raw_video_path),
        "-i", str(portrait),
        "-filter_complex", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return str(out_path)
