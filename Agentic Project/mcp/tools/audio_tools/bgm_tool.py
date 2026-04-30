"""Background music — library-first, synth fallback.

Order of preference, per scene mood:
  1. Real CC-licensed mp3s in `data/bgm/library/{mood}/<file>.mp3`.
     Picked by `MOOD_TO_BGM_FILE`. Looped/trimmed to scene length and
     rendered as a wav for downstream mixing. Run
     `scripts/fetch_bgm.py` once to populate the library from the
     archive.org "Ambient Film Music" CC-BY 3.0 collection.
  2. Multi-oscillator chord pad synthesised in pure ffmpeg lavfi.
     Less refined than real music but reliably audible and
     mood-correlated. Used when the library file is absent.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from config import AUDIO_DIR, ROOT
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import MOOD_TO_BGM, MOOD_TO_BGM_FILE
from shared.utils import hash_short, job_dir

BGM_LIBRARY_ROOT = ROOT / "data" / "bgm" / "library"


def _resolve_library_track(mood: str) -> Optional[Path]:
    """Look up the curated track for `mood`, fall back to any track in
    that mood's directory, then to any track in the library at all."""
    file_hint = MOOD_TO_BGM_FILE.get(mood.lower())
    if file_hint:
        # Search any sub-directory under the library root for the named file
        for cand in BGM_LIBRARY_ROOT.rglob(file_hint):
            if cand.exists():
                return cand
    mood_dir = BGM_LIBRARY_ROOT / mood.lower()
    if mood_dir.exists():
        mp3s = sorted(mood_dir.glob("*.mp3"))
        if mp3s:
            return mp3s[0]
    if BGM_LIBRARY_ROOT.exists():
        mp3s = sorted(BGM_LIBRARY_ROOT.rglob("*.mp3"))
        if mp3s:
            return mp3s[0]
    return None


def _from_library(track: Path, duration_s: float, vol: float, out: Path) -> str:
    """Loop/trim `track` to `duration_s`, normalise, fade in/out, write `out`."""
    fade_in = min(1.0, duration_s / 6.0)
    fade_out = min(1.5, duration_s / 4.0)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-stream_loop", "-1",
        "-i", str(track),
        "-t", f"{duration_s:.3f}",
        "-af", (
            f"loudnorm=I=-22:TP=-2:LRA=11,"
            f"volume={vol},"
            f"afade=t=in:st=0:d={fade_in:.3f},"
            f"afade=t=out:st={max(0.0, duration_s - fade_out):.3f}:d={fade_out:.3f}"
        ),
        "-ar", "24000", "-ac", "1",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return str(out)


def _synth_fallback(mood: str, duration_s: float, vol: float, out: Path) -> str:
    """Multi-oscillator chord pad rendered via lavfi.

    Layers: I, III (minor third = root × 1.189), V (perfect fifth × 1.5),
    plus an octave on V for movement. Each layer gets gentle vibrato.
    Then a soft echo to simulate room ambience and a long fade in/out.
    """
    cfg = MOOD_TO_BGM.get(mood.lower(), MOOD_TO_BGM["neutral"])
    root = cfg["root"]
    minor_third = root * 1.189
    fifth = root * 1.5
    octave_fifth = fifth * 2
    base_amp = max(0.10, min(0.45, vol))
    fade_in = min(1.0, duration_s / 6.0)
    fade_out = min(1.5, duration_s / 4.0)

    def _src(freq: float) -> str:
        return f"sine=frequency={freq:.2f}:duration={duration_s:.3f}"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", _src(root),
        "-f", "lavfi", "-i", _src(minor_third),
        "-f", "lavfi", "-i", _src(fifth),
        "-f", "lavfi", "-i", _src(octave_fifth),
        "-filter_complex",
        (
            f"[0:a]volume={base_amp:.3f},tremolo=f=4.5:d=0.18[a0];"
            f"[1:a]volume={base_amp * 0.62:.3f},tremolo=f=4.0:d=0.15[a1];"
            f"[2:a]volume={base_amp * 0.55:.3f},tremolo=f=3.5:d=0.20[a2];"
            f"[3:a]volume={base_amp * 0.30:.3f}[a3];"
            f"[a0][a1][a2][a3]amix=inputs=4:normalize=0[mix];"
            f"[mix]aecho=0.5:0.6:60|120:0.25|0.18,"
            f"highpass=f=70,lowpass=f=4500,"
            f"afade=t=in:st=0:d={fade_in:.3f},"
            f"afade=t=out:st={max(0.0, duration_s - fade_out):.3f}:d={fade_out:.3f}[out]"
        ),
        "-map", "[out]",
        "-ar", "24000", "-ac", "1",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return str(out)


class BGMTool(BaseTool):
    spec = ToolSpec(
        name="generate_bgm",
        description="Pick a mood-appropriate BGM bed for `duration_ms` ms (real track if available, else synth).",
        category="audio",
        schema={"mood": "str", "duration_ms": "int", "volume": "float"},
    )

    def run(self, mood: str = "neutral", duration_ms: int = 5000, volume: float | None = None,
            job_id: str | None = None) -> str:
        from shared.constants import DEFAULT_BGM_VOLUME
        duration_s = max(duration_ms, 1000) / 1000.0
        vol = volume if volume is not None else DEFAULT_BGM_VOLUME

        track = _resolve_library_track(mood)
        source = "lib" if track else "synth"
        key = hash_short(f"bgm|{mood}|{duration_ms}|{vol}|{source}|{track}")
        out = job_dir(AUDIO_DIR, job_id) / f"bgm_{mood}_{key}.wav"
        if out.exists() and out.stat().st_size > 0:
            return str(out)

        if track:
            return _from_library(track, duration_s, vol, out)
        return _synth_fallback(mood, duration_s, vol, out)
