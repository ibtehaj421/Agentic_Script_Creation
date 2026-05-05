"""Color-grade an existing video clip via ffmpeg.

Used by the edit agent's generalised `modify_scene_visual` intent so
free-text directives like "make scene 1 darker", "more orange",
"warmer", "more saturated" produce visible changes on the rendered
scene MP4 — not just on the unused background image.

The filter graph is `eq=brightness=B:saturation=S, hue=h=H` where:
  brightness ∈ [-1.0, 1.0]    0.0 = unchanged   negative = darker
  saturation ∈ [ 0.0, 3.0]    1.0 = unchanged   <1 = desaturated
  hue_shift  ∈ [-180, 180]    0   = unchanged   degrees of hue rotation
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from config import VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.utils import hash_short, job_dir, video_encoder_args


class VideoColorGradeTool(BaseTool):
    spec = ToolSpec(
        name="apply_video_color_grade",
        description=(
            "Apply brightness/saturation/hue deltas to a video clip via "
            "ffmpeg eq+hue filters. Returns the new MP4 path."
        ),
        category="video",
        schema={
            "video_path": "str",
            "brightness": "float",
            "saturation": "float",
            "hue_shift": "float",
        },
    )

    def run(
        self,
        video_path: str,
        brightness: float = 0.0,
        saturation: float = 1.0,
        hue_shift: float = 0.0,
        job_id: str | None = None,
    ) -> str:
        # Clamp to safe ranges
        brightness = max(-0.5, min(0.5, float(brightness)))
        saturation = max(0.0, min(3.0, float(saturation)))
        hue_shift = max(-180.0, min(180.0, float(hue_shift)))

        # Identity short-circuit
        if abs(brightness) < 0.001 and abs(saturation - 1.0) < 0.001 and abs(hue_shift) < 0.5:
            return video_path

        src = Path(video_path)
        key = hash_short(f"grade|{video_path}|{brightness:.3f}|{saturation:.3f}|{hue_shift:.3f}")
        out = job_dir(VIDEO_DIR, job_id) / f"grade_{src.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        eq_chain = []
        if abs(brightness) >= 0.001 or abs(saturation - 1.0) >= 0.001:
            eq_chain.append(f"eq=brightness={brightness:.3f}:saturation={saturation:.3f}")
        if abs(hue_shift) >= 0.5:
            eq_chain.append(f"hue=h={hue_shift:.2f}")
        vf = ",".join(eq_chain) if eq_chain else "null"

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src),
                "-vf", vf,
                *video_encoder_args(bitrate="6M"),
                "-c:a", "copy",
                str(out),
            ],
            check=True,
        )
        return str(out)
