"""Stock footage tool — free, keyless.

Generates a short MP4 clip per scene:
    1. fetches a scene-specific background still from Pollinations
       (free, keyless) using location + visual_cue + action as the prompt,
    2. bakes a caption band describing the scene onto the still,
    3. applies a Ken-Burns zoom/pan with ffmpeg.

Every scene therefore gets a visually distinct backdrop, not a repeat of
the primary character's portrait.
"""
from __future__ import annotations

import hashlib
import subprocess
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import httpx

# Serialize Pollinations requests so parallel scene branches don't trigger
# the endpoint's per-IP rate limit (429).
_POLLINATIONS_LOCK = threading.Lock()

from config import VIDEO_OUT_DIR, resolve_character_image

DEFAULT_DURATION = 5.0  # seconds per scene clip
TARGET_SIZE = (640, 360)


SCENE_BG_DIR = VIDEO_OUT_DIR / "scene_backgrounds"


def _fallback_image() -> Path:
    """Plain gradient used only when all else fails."""
    from PIL import Image
    out = VIDEO_OUT_DIR / "_fallback_bg.png"
    if out.exists():
        return out
    img = Image.new("RGB", TARGET_SIZE, color=(20, 20, 35))
    img.save(out)
    return out


def _fetch_scene_background(
    location: str, visual_cue: str, action: str, cache_key: str
) -> Path:
    """Pull a scene-specific background from Pollinations (free, keyless).

    Falls back to the character portrait or a gradient if the remote
    endpoint is unreachable.
    """
    SCENE_BG_DIR.mkdir(parents=True, exist_ok=True)
    out = SCENE_BG_DIR / f"bg_{cache_key}.png"
    if out.exists() and out.stat().st_size > 4_000:
        return out

    prompt = (
        f"cinematic wide shot of {location}, {visual_cue}, {action}, "
        f"atmospheric lighting, photorealistic, 16:9, ultra detailed, no text, no watermark"
    )
    encoded = urllib.parse.quote(prompt)
    base = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=768&height=432&nologo=true"
    )

    last_err: Exception | None = None
    with _POLLINATIONS_LOCK:
        for attempt in range(5):
            try:
                url = base + f"&seed={uuid.uuid4().int % 1_000_000}"
                r = httpx.get(url, timeout=180, follow_redirects=True)
                if r.status_code == 429:
                    wait = 10 * (attempt + 1)
                    print(f"  ⏳ pollinations 429 on scene {cache_key[:6]}; sleeping {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if r.content and ctype.startswith("image") and len(r.content) > 4_000:
                    out.write_bytes(r.content)
                    # polite pacing so neighbouring threads don't slam the API
                    time.sleep(2)
                    return out
                last_err = RuntimeError(f"non-image or tiny response: {ctype} {len(r.content)}b")
            except Exception as e:
                last_err = e
            time.sleep(5 * (attempt + 1))

    print(f"  ⚠ pollinations failed for scene bg {cache_key[:6]}: {last_err}")
    return _fallback_image()


def _burn_caption(src: Path, caption: str) -> Path:
    """Bake a caption strip onto a copy of `src` using Pillow.

    Used instead of ffmpeg's drawtext filter, which requires a
    libfreetype-enabled ffmpeg build (not available in Homebrew's default).
    """
    from PIL import Image, ImageDraw, ImageFont

    out = VIDEO_OUT_DIR / f"_captioned_{src.stem}_{abs(hash(caption)) % 10**8}.png"
    if out.exists():
        return out

    img = Image.open(src).convert("RGB").resize(TARGET_SIZE)
    draw = ImageDraw.Draw(img, "RGBA")
    # Gradient bottom band
    band_h = 110
    for i in range(band_h):
        alpha = int(180 * (i / band_h))
        draw.rectangle(
            (0, TARGET_SIZE[1] - band_h + i, TARGET_SIZE[0], TARGET_SIZE[1] - band_h + i + 1),
            fill=(0, 0, 0, alpha),
        )
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 22
        )
    except OSError:
        font = ImageFont.load_default()
    # Naive word-wrap to fit inside the frame
    words, lines, line = caption.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > 70:
            lines.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        lines.append(line)
    y = TARGET_SIZE[1] - band_h + 20
    for l in lines[:3]:
        draw.text((40, y), l, fill=(255, 255, 255), font=font)
        y += 28
    img.save(out)
    return out


def query_stock_footage(
    location: str,
    visual_cue: str,
    action: str,
    character_image: str | None = None,
    duration: float = DEFAULT_DURATION,
) -> str:
    """Build a raw scene clip from `character_image` (if provided) with
    subtle pan/zoom, and bake a scene-caption describing the location +
    visual cue onto the bottom of the frame. Returns an MP4 path."""
    key = hashlib.md5(
        f"{location}|{visual_cue}|{action}|{character_image}|{duration}"
        .encode("utf-8")
    ).hexdigest()[:12]
    out_path = VIDEO_OUT_DIR / f"raw_{key}.mp4"
    if out_path.exists() and out_path.stat().st_size > 0:
        return str(out_path)

    bg = _fetch_scene_background(location, visual_cue, action, cache_key=key)
    if not bg.exists():
        bg = Path(character_image) if character_image else _fallback_image()
    source = _burn_caption(bg, f"{location} — {visual_cue.strip()[:120]}")

    w, h = TARGET_SIZE
    fps = 25
    frames = int(duration * fps)
    # zoompan with d=1 outputs one frame per input frame (clean timing);
    # the t=N expression drives the zoom animation explicitly.
    zoom_expr = (
        f"zoompan=z='1+0.12*on/{frames}':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
    )
    vf = (
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
        f"crop={w*2}:{h*2},{zoom_expr}"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-t", f"{duration}",
        "-i", str(source),
        "-vf", vf,
        "-t", f"{duration}",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return str(out_path)
