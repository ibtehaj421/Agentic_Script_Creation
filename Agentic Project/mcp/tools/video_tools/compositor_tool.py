"""Scene-level and final-output compositors.

SceneComposeTool assembles ONE scene's MP4:
   Ken-Burns still → portrait overlay → A/V sync → (optional) subtitle burn

FinalCompositorTool stitches N scene MP4s into a single final MP4 with
xfade transitions between them.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from config import FINAL_DIR, SCENES_DIR, VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import TRANSITION_DURATION_S
from shared.utils import hash_short, job_dir, probe_duration, video_encoder_args


class SceneComposeTool(BaseTool):
    spec = ToolSpec(
        name="compose_scene",
        description=(
            "Loop a Ken-Burns clip to audio length and mux with the dialogue/BGM "
            "audio track. Returns the scene MP4 path."
        ),
        category="video",
    )

    def run(self, video_path: str, audio_path: str, scene_id: int, job_id: str = "") -> str:
        # Job-scoped output dir. Without this, two jobs that both render
        # `scene_01.mp4` in SCENES_DIR clobber each other's working files
        # (the per-line scene_NN.mp4 files in the close-up flow as well),
        # causing cross-job contamination after the second job runs.
        scenes_dir = SCENES_DIR / job_id if job_id else SCENES_DIR
        scenes_dir.mkdir(parents=True, exist_ok=True)
        out = scenes_dir / f"scene_{scene_id:02d}.mp4"

        audio_duration = probe_duration(audio_path)

        filter_complex = (
            f"[0:v]loop=loop=-1:size=32767:start=0,trim=end={audio_duration:.3f},"
            f"setpts=PTS-STARTPTS[v]"
        )

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "1:a",
                *video_encoder_args(bitrate="6M"),
                "-c:a", "aac", "-b:a", "160k",
                "-shortest",
                str(out),
            ],
            check=True,
        )
        return str(out)


class FinalCompositorTool(BaseTool):
    spec = ToolSpec(
        name="compose_final",
        description="Stitch ordered scene MP4s into a single final MP4 with xfade transitions.",
        category="video",
        schema={"scene_paths": "list[str]", "out_name": "str", "transition": "one_of(xfade, cut, fade)"},
    )

    def run(
        self,
        scene_paths: List[str],
        out_name: str = "final_output.mp4",
        transition: str = "fade",
        xfade_duration: float = TRANSITION_DURATION_S,
        job_id: str | None = None,
    ) -> str:
        if not scene_paths:
            raise ValueError("no scene paths to compose")

        out = FINAL_DIR / out_name
        if len(scene_paths) == 1:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", scene_paths[0],
                    *video_encoder_args(bitrate="6M"),
                    "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart",
                    str(out),
                ],
                check=True,
            )
            return str(out)

        if transition == "cut":
            return self._concat_cut(scene_paths, out, job_id)
        return self._concat_xfade(scene_paths, out, xfade_duration, job_id)

    def _concat_cut(self, paths: List[str], out: Path, job_id: str | None = None) -> str:
        list_file = job_dir(VIDEO_DIR, job_id) / f"_concat_{hash_short(str(paths))}.txt"
        list_file.write_text("\n".join(f"file '{p}'" for p in paths))
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                *video_encoder_args(bitrate="6M"),
                "-c:a", "aac", "-b:a", "160k",
                # Move the moov atom to the start so browsers can begin
                # progressive playback before the whole file is buffered.
                "-movflags", "+faststart",
                str(out),
            ],
            check=True,
        )
        return str(out)

    def _concat_xfade(self, paths: List[str], out: Path, xfade_s: float, job_id: str | None = None) -> str:
        durations = [probe_duration(p) for p in paths]

        input_args: List[str] = []
        for p in paths:
            input_args.extend(["-i", p])

        offsets: List[float] = []
        acc = 0.0
        for i in range(len(paths) - 1):
            acc += durations[i] - xfade_s
            offsets.append(acc)

        v_parts: List[str] = []
        prev = "[0:v]"
        for i in range(1, len(paths)):
            nxt = f"[{i}:v]"
            out_label = f"[vx{i}]"
            v_parts.append(
                f"{prev}{nxt}xfade=transition=fade:duration={xfade_s}:offset={offsets[i-1]:.3f}{out_label}"
            )
            prev = out_label

        a_parts: List[str] = []
        prev_a = "[0:a]"
        for i in range(1, len(paths)):
            nxt_a = f"[{i}:a]"
            out_label = f"[ax{i}]"
            a_parts.append(
                f"{prev_a}{nxt_a}acrossfade=d={xfade_s}{out_label}"
            )
            prev_a = out_label

        fc = ";".join(v_parts + a_parts)

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                *input_args,
                "-filter_complex", fc,
                "-map", prev, "-map", prev_a,
                *video_encoder_args(bitrate="6M"),
                "-c:a", "aac", "-b:a", "160k",
                # Move the moov atom to the start so browsers can begin
                # progressive playback before the whole file is buffered.
                "-movflags", "+faststart",
                str(out),
            ],
            check=True,
        )
        return str(out)
