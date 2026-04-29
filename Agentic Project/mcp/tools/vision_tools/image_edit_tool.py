"""Non-generative image edits: brightness/contrast/saturation/hue tint.

Used by the edit agent to implement queries like "make the scene darker"
without re-running expensive generation.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance

from config import VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.utils import hash_short, job_dir


class ImageColorAdjustTool(BaseTool):
    spec = ToolSpec(
        name="adjust_image_color",
        description="Apply brightness/contrast/saturation multipliers to an image. Returns new path.",
        category="vision",
        schema={"src_path": "str", "brightness": "float", "contrast": "float", "saturation": "float"},
    )

    def run(
        self,
        src_path: str,
        brightness: float = 1.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        job_id: str | None = None,
    ) -> str:
        src = Path(src_path)
        key = hash_short(f"{src_path}|{brightness}|{contrast}|{saturation}")
        out = job_dir(VIDEO_DIR, job_id) / f"_adj_{src.stem}_{key}.png"
        if out.exists():
            return str(out)

        img = Image.open(src).convert("RGB")
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)
        img.save(out)
        return str(out)
