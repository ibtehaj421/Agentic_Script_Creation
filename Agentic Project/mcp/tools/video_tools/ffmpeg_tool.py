"""Low-level ffmpeg building blocks.

Three primitives the scene compositor assembles:
  * Ken-Burns still → motion clip
  * portrait overlay (bottom-left circular cut-out)
  * speed adjustment (for "speed up this scene" edits)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from config import VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import TARGET_FPS, TARGET_HEIGHT, TARGET_WIDTH
from shared.utils import hash_short, job_dir, video_encoder_args


# Portrait overlay size scales with frame height — looks roughly the same
# proportion at 540p and 1080p.
PORTRAIT_OVERLAY_SIZE = max(180, int(TARGET_HEIGHT * 0.22))   # ~240 px at 1080p
PORTRAIT_OVERLAY_MARGIN = max(28, int(TARGET_HEIGHT * 0.04))  # ~44 px at 1080p


def _circular_portrait(src: Path, size: int = PORTRAIT_OVERLAY_SIZE) -> Path:
    out = VIDEO_DIR / f"_portrait_{src.stem}_{size}.png"
    if out.exists():
        return out
    img = Image.open(src).convert("RGBA").resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    img.putalpha(mask)
    # Add a subtle white ring for visual separation from the background
    ring_thickness = max(2, size // 60)
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.ellipse(
        (ring_thickness, ring_thickness, size - ring_thickness, size - ring_thickness),
        outline=(255, 255, 255, 200),
        width=ring_thickness,
    )
    img = Image.alpha_composite(img, ring)
    img.save(out)
    return out


class KenBurnsTool(BaseTool):
    spec = ToolSpec(
        name="ken_burns",
        description="Zoom/pan a still into an MP4 of `duration_s` at TARGET_WIDTHxTARGET_HEIGHT.",
        category="video",
        schema={"image_path": "str", "duration_s": "float", "direction": "one_of(zoom_in, zoom_out, pan_left, pan_right)"},
    )

    def run(self, image_path: str, duration_s: float = 5.0, direction: str = "zoom_in",
            job_id: str | None = None) -> str:
        src = Path(image_path)
        # `topcrop` tag in the cache key invalidates pre-fix kb_*.mp4 files
        # which were rendered with a centered (face-cutting) crop.
        key = hash_short(f"{image_path}|{duration_s:.2f}|{direction}|{TARGET_WIDTH}x{TARGET_HEIGHT}|topcrop")
        out = job_dir(VIDEO_DIR, job_id) / f"kb_{src.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        w, h, fps = TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS
        frames = max(int(duration_s * fps), 2)

        if direction == "zoom_out":
            z = f"1.2-0.12*on/{frames}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif direction == "pan_left":
            z = "1.1"
            x = f"(iw-iw/1.1)*((1-on/{frames}))"
            y = "(ih-ih/1.1)/2"
        elif direction == "pan_right":
            z = "1.1"
            x = f"(iw-iw/1.1)*(on/{frames})"
            y = "(ih-ih/1.1)/2"
        else:  # zoom_in (default)
            z = f"1+0.10*on/{frames}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"

        zoompan = (
            f"zoompan=z='{z}':d=1:"
            f"x='{x}':y='{y}':s={w}x{h}:fps={fps}"
        )
        # No prescale — render at source resolution. Pollinations delivers
        # 1024×576 natively, which matches our target, so any extra scale
        # step would be a pure upscale.
        #
        # Crop is *centered horizontally* (x=(iw-w)/2) but *top-aligned
        # vertically* (y=0). Square character portraits placed faces in
        # the upper half, so the previous default-centered crop sliced
        # the face off. Top-aligning keeps the face in-frame for close-ups
        # and is identity (a no-op) for already-16:9 backgrounds.
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}:(iw-{w})/2:0,{zoompan}"
        )

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-loop", "1", "-t", f"{duration_s}",
                "-i", str(src),
                "-vf", vf,
                "-t", f"{duration_s}",
                "-r", str(fps),
                *video_encoder_args(bitrate="6M"),
                str(out),
            ],
            check=True,
        )
        return str(out)


class PortraitOverlayTool(BaseTool):
    spec = ToolSpec(
        name="overlay_portrait",
        description="Overlay a circular portrait of `portrait_path` in the bottom-left of `video_path`.",
        category="video",
        schema={"video_path": "str", "portrait_path": "str", "label": "str"},
    )

    def run(self, video_path: str, portrait_path: str, label: str = "", size: int = PORTRAIT_OVERLAY_SIZE,
            job_id: str | None = None) -> str:
        video = Path(video_path)
        key = hash_short(f"{video_path}|{portrait_path}|{label}|{size}|v2")
        out = job_dir(VIDEO_DIR, job_id) / f"ov_{video.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        portrait = _circular_portrait(Path(portrait_path), size=size)
        margin = PORTRAIT_OVERLAY_MARGIN

        vf = (
            f"[1:v]scale={size}:{size}[p];"
            f"[0:v][p]overlay=x={margin}:y=H-h-{margin}:format=auto"
        )

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-i", str(portrait),
                "-filter_complex", vf,
                *video_encoder_args(bitrate="6M"),
                str(out),
            ],
            check=True,
        )
        return str(out)


class SpeedAdjustTool(BaseTool):
    spec = ToolSpec(
        name="adjust_speed",
        description="Playback-speed adjustment (0.5-2.0). Used by edit queries like 'speed up this scene'.",
        category="video",
        schema={"video_path": "str", "speed": "float"},
    )

    def run(self, video_path: str, speed: float = 1.0, job_id: str | None = None) -> str:
        speed = max(0.5, min(2.0, speed))
        key = hash_short(f"{video_path}|{speed:.3f}|v2")
        video = Path(video_path)
        out = job_dir(VIDEO_DIR, job_id) / f"sp_{video.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        # setpts for video (1/speed); atempo for audio (audio accepts 0.5..2)
        fc = (
            f"[0:v]setpts=PTS/{speed}[v];"
            f"[0:a]atempo={speed}[a]"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-filter_complex", fc,
                "-map", "[v]", "-map", "[a]",
                *video_encoder_args(bitrate="6M"),
                "-c:a", "aac", "-b:a", "128k",
                str(out),
            ],
            check=True,
        )
        return str(out)
