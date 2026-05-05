"""Merge / duck audio tracks with ffmpeg.

Two operations the pipeline needs:
  * concat_wavs — stitch per-line TTS wavs into one scene dialogue track.
  * mix_with_bgm — layer dialogue over BGM, ducking BGM where dialogue exists.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from config import AUDIO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.utils import hash_short, job_dir, probe_duration


class AudioMergerTool(BaseTool):
    spec = ToolSpec(
        name="merge_audio",
        description=(
            "op=concat: stitch wavs; op=mix_bgm: mix dialogue over BGM (BGM ducks to ~20% during dialogue)."
        ),
        category="audio",
        schema={"op": "one_of(concat, mix_bgm)", "paths": "list[str]", "dialogue": "str", "bgm": "str", "out_stem": "str"},
    )

    def run(
        self,
        op: str,
        paths: list[str] | None = None,
        dialogue: str | None = None,
        bgm: str | None = None,
        out_stem: str = "merged",
        job_id: str | None = None,
    ) -> str:
        if op == "concat":
            return self._concat(paths or [], out_stem, job_id)
        if op == "mix_bgm":
            if not dialogue or not bgm:
                raise ValueError("mix_bgm needs `dialogue` and `bgm` paths")
            return self._mix_bgm(dialogue, bgm, out_stem, job_id)
        raise ValueError(f"unknown op: {op}")

    def _concat(self, paths: list[str], stem: str, job_id: str | None = None) -> str:
        if not paths:
            raise ValueError("no paths to concat")
        key = hash_short("|".join(paths))
        out = job_dir(AUDIO_DIR, job_id) / f"{stem}_{key}.wav"
        if out.exists():
            return str(out)

        if len(paths) == 1:
            import shutil
            shutil.copy(paths[0], out)
            return str(out)

        inputs: list[str] = []
        for p in paths:
            inputs.extend(["-i", p])
        fc = (
            "".join(f"[{i}:a]" for i in range(len(paths)))
            + f"concat=n={len(paths)}:v=0:a=1[out]"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *inputs,
             "-filter_complex", fc, "-map", "[out]", str(out)],
            check=True,
        )
        return str(out)

    def _mix_bgm(self, dialogue: str, bgm: str, stem: str, job_id: str | None = None) -> str:
        key = hash_short(f"{dialogue}|{bgm}|v3")
        out = job_dir(AUDIO_DIR, job_id) / f"{stem}_{key}.wav"
        if out.exists():
            return str(out)

        dlg_len = probe_duration(dialogue)
        # Static-bed mixing: BGM at -12 dBFS (volume=0.25), dialogue at unity.
        # Sidechain ducking sounded great in theory but in practice (with
        # tts that already varies in level) it aggressively suppressed the
        # BGM into inaudibility. A simple level mix gives a crisp,
        # dialogue-forward bed that's still clearly audible underneath.
        fc = (
            f"[1:a]aloop=loop=-1:size=2e9,atrim=duration={dlg_len},"
            f"volume=0.45[bgm];"
            f"[0:a]volume=1.0[dlg];"
            f"[dlg][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", dialogue, "-i", bgm,
                "-filter_complex", fc,
                "-map", "[out]",
                "-ar", "24000", "-ac", "1",
                str(out),
            ],
            check=True,
        )
        return str(out)
