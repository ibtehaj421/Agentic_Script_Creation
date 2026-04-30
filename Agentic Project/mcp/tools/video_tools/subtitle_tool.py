"""Subtitle burning — Pillow overlays, libass-free.

Homebrew's default ffmpeg ships without libass, so the `subtitles` and
`ass` filters are unavailable. Instead we pre-render each dialogue line
as a transparent PNG with anti-aliased text, then overlay it on the
scene MP4 for its time range using ffmpeg's `overlay` filter with an
`enable='between(t,a,b)'` gate. This keeps timing accurate (millisecond
precision), needs no extra dependencies, and always works.

`write_srt` is kept around so the video is still accompanied by a
sidecar .srt — useful for accessibility and for verifying timing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont

from config import VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import TARGET_HEIGHT, TARGET_WIDTH
from shared.utils import hash_short, job_dir


def _fmt_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def write_srt(segments: List[dict], out_path: Path) -> Path:
    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(seg['start_s'])} --> {_fmt_ts(seg['end_s'])}")
        lines.append(seg["text"].strip())
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _caption_png(text: str, width: int = TARGET_WIDTH) -> Path:
    """Render `text` as an RGBA PNG band ~2 lines tall, centred horizontally.

    Sizing scales with the target width so 1080p doesn't get pebble-sized
    captions.
    """
    font_size = max(28, int(width * 0.022))   # ~42 px at 1920p, ~28 px at 1280p
    line_h = int(font_size * 1.32)
    band_h = line_h * 2 + 40
    img = Image.new("RGBA", (width, band_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except OSError:
            font = ImageFont.load_default()

    # Word-wrap to fit; max 2 lines
    words = text.split()
    lines: list[str] = []
    line = ""
    for w in words:
        probe = f"{line} {w}".strip()
        if draw.textlength(probe, font=font) < width - 120:
            line = probe
        else:
            if line:
                lines.append(line)
            line = w
            if len(lines) >= 2:
                break
    if line and len(lines) < 2:
        lines.append(line)
    if not lines:
        lines = [text]

    total_text_h = len(lines) * line_h
    y = band_h - total_text_h - 12
    for l in lines:
        tw = draw.textlength(l, font=font)
        x_text = (width - tw) / 2
        pad_x, pad_y = int(font_size * 0.6), int(font_size * 0.18)
        draw.rounded_rectangle(
            (x_text - pad_x, y - pad_y, x_text + tw + pad_x, y + line_h * 0.92 + pad_y),
            radius=int(font_size * 0.4),
            fill=(0, 0, 0, 180),
        )
        # drop shadow + text
        draw.text((x_text + 2, y + 2), l, font=font, fill=(0, 0, 0, 220))
        draw.text((x_text, y), l, font=font, fill=(255, 255, 255, 255))
        y += line_h

    key = hash_short(f"{text}|{font_size}")
    out = VIDEO_DIR / f"_caption_{key}.png"
    img.save(out)
    return out


class SubtitleBurnTool(BaseTool):
    spec = ToolSpec(
        name="burn_subtitles",
        description=(
            "Burn time-gated Pillow-rendered caption overlays onto an MP4. "
            "Also writes a sidecar .srt for accessibility."
        ),
        category="video",
        schema={"video_path": "str", "segments": "list[dict]"},
    )

    def run(self, video_path: str, segments: List[dict], job_id: str | None = None, **_) -> str:
        video = Path(video_path)
        if not segments:
            return video_path

        # Include input mtime+size in the cache key so we don't serve
        # stale subtitled output when upstream tools (compose_scene)
        # overwrite the source file at the same path with new content.
        try:
            st = video.stat()
            content_tag = f"{int(st.st_mtime_ns)}|{st.st_size}"
        except OSError:
            content_tag = "missing"
        key = hash_short(f"{video_path}|{content_tag}|{str(segments)}")
        out_dir = job_dir(VIDEO_DIR, job_id)
        out = out_dir / f"sub_{video.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        # Sidecar SRT (not used by the filter, but nice to have)
        write_srt(segments, out_dir / f"{video.stem}_{key}.srt")

        # Render one PNG per segment, then build an overlay chain.
        caption_paths = [_caption_png(seg["text"]) for seg in segments]

        input_args: list[str] = ["-i", str(video)]
        for p in caption_paths:
            input_args.extend(["-i", str(p)])

        # Position caption band relative to frame height (~7% from bottom).
        # Need to know caption height to nail the offset; we know it from
        # _caption_png: font_size * 1.32 * 2 + 40 ≈ 152 px at 1080p.
        y_offset = max(TARGET_HEIGHT - int(TARGET_HEIGHT * 0.21), 0)
        filter_parts: list[str] = []
        prev = "[0:v]"
        for i, seg in enumerate(segments, start=1):
            label_out = f"[v{i}]"
            filter_parts.append(
                f"{prev}[{i}:v]overlay=x=(W-w)/2:y={y_offset}:"
                f"enable='between(t,{seg['start_s']:.3f},{seg['end_s']:.3f})'"
                f"{label_out}"
            )
            prev = label_out

        fc = ";".join(filter_parts)

        from shared.utils import video_encoder_args
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    *input_args,
                    "-filter_complex", fc,
                    "-map", prev, "-map", "0:a?",
                    *video_encoder_args(bitrate="6M"),
                    "-c:a", "copy",
                    str(out),
                ],
                check=True,
            )
            return str(out)
        except subprocess.CalledProcessError:
            print("  ⚠ subtitle overlay failed; returning video without captions")
            return video_path
