"""Lightweight OpenCV-based 'style overlays' — sepia, noir, cyberpunk tint.

Intentionally not a neural style transfer: we just push the hue/saturation
in a stylised direction so edits feel instant. Matches the Phase 5 spec's
hint ("store a collection of filters and apply on user query").
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from config import VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.utils import hash_short, job_dir


STYLE_LUTS = {
    "sepia":     np.array([[0.272, 0.534, 0.131],
                           [0.349, 0.686, 0.168],
                           [0.393, 0.769, 0.189]]),
    "noir":      "noir",       # handled specially
    "cyberpunk": "cyberpunk",
    "warm":      np.array([[1.0, 0.0, 0.0],
                           [0.0, 1.05, 0.0],
                           [0.0, 0.0, 1.15]]),  # BGR: boost red, trim blue
    "cold":      np.array([[1.15, 0.0, 0.0],
                           [0.0, 1.0, 0.0],
                           [0.0, 0.0, 0.9]]),
    "vivid":     "vivid",
    "vintage":   "vintage",
}


def _apply_matrix(bgr: np.ndarray, mat: np.ndarray) -> np.ndarray:
    # OpenCV is BGR; the sepia matrix we have is RGB-ordered. Swap.
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    flat = rgb.reshape(-1, 3).astype(np.float32) @ mat.T
    flat = np.clip(flat, 0, 255).astype(np.uint8)
    out_rgb = flat.reshape(rgb.shape)
    return cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)


class StyleOverlayTool(BaseTool):
    spec = ToolSpec(
        name="apply_style_filter",
        description="Apply a named stylistic colour grade to an image. Returns new path.",
        category="vision",
        schema={"src_path": "str", "filter": "one_of(sepia, noir, cyberpunk, warm, cold, vivid, vintage)"},
    )

    def run(self, src_path: str, filter: str = "sepia", job_id: str | None = None) -> str:
        src = Path(src_path)
        key = hash_short(f"{src_path}|{filter}")
        out = job_dir(VIDEO_DIR, job_id) / f"_styled_{src.stem}_{key}_{filter}.png"
        if out.exists():
            return str(out)

        img = cv2.imread(str(src))
        if img is None:
            raise FileNotFoundError(src)

        filt = STYLE_LUTS.get(filter.lower(), "vivid")
        if isinstance(filt, np.ndarray):
            styled = _apply_matrix(img, filt)
        elif filt == "noir":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            styled = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            styled = cv2.convertScaleAbs(styled, alpha=1.2, beta=-15)
        elif filt == "cyberpunk":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
            hsv[..., 0] = (hsv[..., 0] + 20) % 180     # hue shift toward magenta
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.3, 0, 255)
            hsv[..., 2] = np.clip(hsv[..., 2] * 1.05, 0, 255)
            styled = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        elif filt == "vivid":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.4, 0, 255)
            styled = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        elif filt == "vintage":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
            hsv[..., 1] = np.clip(hsv[..., 1] * 0.7, 0, 255)
            bgr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
            styled = cv2.convertScaleAbs(bgr, alpha=0.9, beta=10)
        else:
            styled = img

        cv2.imwrite(str(out), styled)
        return str(out)
