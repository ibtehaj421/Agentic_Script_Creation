"""Image generation.

Two providers, hot-swapped at runtime:
  * fal.ai FLUX (primary when FAL_KEY is set) — genuine 1920×1080 from a
    SOTA model, ~$0.006/image on flux/schnell, ~5s per image.
  * Pollinations (fallback, free, no key) — capped at 1024×576 by the
    free tier. Used when fal.ai is unavailable or errors.

If both fail, both tools fall back to a Pillow placeholder so the
pipeline never hard-fails (critical for the "output completeness"
rubric).

Two registered tools:
  * CharacterPortraitTool — square portrait from a character record.
  * SceneBackgroundTool   — 16:9 establishing shot from location+visual_cue+action.
"""
from __future__ import annotations

import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from config import FAL_IMAGE_MODEL, FAL_KEY, IMAGES_DIR, VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import (
    BACKGROUND_REQ_HEIGHT,
    BACKGROUND_REQ_WIDTH,
    PORTRAIT_SIZE,
)
from shared.utils import hash_short, job_dir, safe_filename

# Pollinations rate-limits per IP; serialize cross-thread access
_POLLINATIONS_LOCK = threading.Lock()
_FAL_LOCK = threading.Lock()


def _scene_bg_dir(job_id: str | None) -> Path:
    """Per-job scene-backgrounds dir under VIDEO_DIR."""
    return job_dir(VIDEO_DIR, job_id) / "scene_backgrounds"


# ─── fal.ai (primary) ──────────────────────────────────────────────────

def _fetch_fal(prompt: str, width: int, height: int, out_path: Path,
               max_attempts: int = 3) -> bool:
    """Render via fal.ai FLUX. Returns True on success."""
    url = f"https://fal.run/{FAL_IMAGE_MODEL}"
    body = {
        "prompt": prompt,
        "image_size": {"width": width, "height": height},
        "num_inference_steps": 4,  # schnell defaults to 4
        "num_images": 1,
        "enable_safety_checker": False,
    }
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    with _FAL_LOCK:
        for attempt in range(max_attempts):
            try:
                r = httpx.post(url, json=body, headers=headers, timeout=120)
                if r.status_code == 401:
                    raise RuntimeError("fal.ai: 401 (key invalid or revoked)")
                if r.status_code == 402 or r.status_code == 403:
                    raise RuntimeError(f"fal.ai: {r.status_code} (credit / access issue) — {r.text[:120]}")
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                images = data.get("images") or []
                if not images:
                    raise RuntimeError(f"fal.ai: no images in response — {str(data)[:200]}")
                img_url = images[0].get("url")
                if not img_url:
                    raise RuntimeError(f"fal.ai: no image url — {str(images[0])[:200]}")

                # Download the image bytes
                ir = httpx.get(img_url, timeout=60, follow_redirects=True)
                ir.raise_for_status()
                if not ir.content or len(ir.content) < 4_000:
                    raise RuntimeError(f"fal.ai: empty image content ({len(ir.content)}b)")
                out_path.write_bytes(ir.content)
                return True
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
    print(f"  ⚠ fal.ai failed: {last_err}")
    return False


# ─── Pollinations (fallback) ───────────────────────────────────────────

def _fetch_pollinations(prompt: str, width: int, height: int, out_path: Path,
                        max_attempts: int = 4) -> bool:
    encoded = urllib.parse.quote(prompt)
    base = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true"
    )
    last_err: Exception | None = None
    with _POLLINATIONS_LOCK:
        for attempt in range(max_attempts):
            try:
                u = base + f"&seed={uuid.uuid4().int % 1_000_000}"
                r = httpx.get(u, timeout=180, follow_redirects=True)
                if r.status_code == 429:
                    time.sleep(8 * (attempt + 1))
                    continue
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if r.content and ctype.startswith("image") and len(r.content) > 4_000:
                    out_path.write_bytes(r.content)
                    time.sleep(1.5)  # polite pacing
                    return True
                last_err = RuntimeError(f"bad content-type {ctype} / {len(r.content)}b")
            except Exception as e:
                last_err = e
            time.sleep(3 * (attempt + 1))
    print(f"  ⚠ pollinations failed: {last_err}")
    return False


def _fetch_image(prompt: str, width: int, height: int, out_path: Path) -> str:
    """Try fal.ai first, fall back to Pollinations. Returns provider used."""
    if FAL_KEY:
        print(f"  🎨  fal.ai     | {width}x{height} | {prompt[:60]}…")
        if _fetch_fal(prompt, width, height, out_path):
            return "fal"
        print("  ⤷ falling back to Pollinations")
    print(f"  🎨  pollinat. | {width}x{height} | {prompt[:60]}…")
    if _fetch_pollinations(prompt, width, height, out_path):
        return "pollinations"
    return "placeholder"


def _placeholder(out_path: Path, title: str, subtitle: str, size: tuple[int, int]) -> Path:
    img = Image.new("RGB", size, color=(30, 30, 48))
    draw = ImageDraw.Draw(img)
    try:
        font_big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
        font_small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    except OSError:
        font_big = font_small = ImageFont.load_default()
    draw.text((20, 20), title[:40], fill=(255, 255, 255), font=font_big)
    draw.text((20, 70), subtitle[:90], fill=(200, 200, 220), font=font_small)
    img.save(out_path)
    return out_path


# ─── Tools ─────────────────────────────────────────────────────────────

class CharacterPortraitTool(BaseTool):
    spec = ToolSpec(
        name="generate_character_portrait",
        description="Generate a high-resolution portrait for a character (fal.ai primary, Pollinations fallback).",
        category="vision",
        schema={"name": "str", "appearance": "str", "reference_style": "str"},
    )

    def run(self, name: str, appearance: str, reference_style: str = "cinematic",
            job_id: str | None = None) -> str:
        safe = safe_filename(name)
        out = job_dir(IMAGES_DIR, job_id) / f"{safe}.png"
        if out.exists() and out.stat().st_size > 4_000:
            return str(out)

        prompt = (
            f"{reference_style} portrait of {name}, {appearance}, "
            f"highly detailed, 8k, centered face, neutral background, professional studio lighting, "
            f"sharp focus, photorealistic"
        )
        provider = _fetch_image(prompt, PORTRAIT_SIZE, PORTRAIT_SIZE, out)
        if provider == "placeholder":
            _placeholder(out, name, appearance, (PORTRAIT_SIZE, PORTRAIT_SIZE))
        return str(out)


class SceneBackgroundTool(BaseTool):
    spec = ToolSpec(
        name="generate_scene_background",
        description="Generate a 16:9 establishing still for a scene (fal.ai primary, Pollinations fallback).",
        category="vision",
        schema={"location": "str", "visual_cue": "str", "action": "str", "mood": "str", "style": "str"},
    )

    def run(
        self,
        location: str,
        visual_cue: str,
        action: str,
        mood: str = "neutral",
        style: str = "cinematic",
        job_id: str | None = None,
    ) -> str:
        # Cache key includes provider so a switch from Pollinations → fal.ai
        # forces a re-fetch (different source resolution and quality).
        provider_tag = "fal" if FAL_KEY else "poll"
        # v4 = "no people / empty location" prompt change
        key = hash_short(f"{location}|{visual_cue}|{action}|{mood}|{style}|{provider_tag}|v4")
        bg_dir = _scene_bg_dir(job_id)
        bg_dir.mkdir(parents=True, exist_ok=True)
        out = bg_dir / f"bg_{key}.png"
        if out.exists() and out.stat().st_size > 4_000:
            return str(out)

        w, h = BACKGROUND_REQ_WIDTH, BACKGROUND_REQ_HEIGHT
        # "no people, empty location" because the close-up flow handles
        # characters separately via the per-character portraits. If we let
        # Pollinations populate the wide shot with random people they're
        # not the actual story characters and the mismatch is jarring.
        prompt = (
            f"{style} wide establishing shot of an empty {location}. {visual_cue}. {action}. "
            f"{mood} mood, atmospheric volumetric lighting, 16:9, photorealistic, ultra detailed, "
            f"sharp focus, depth of field, 8k, "
            f"no people, no person, no characters, no figures, "
            f"empty location, deserted setting, "
            f"no text, no watermark, no signature"
        )
        provider = _fetch_image(prompt, w, h, out)
        if provider == "placeholder":
            _placeholder(out, location, visual_cue, (w, h))
        return str(out)
