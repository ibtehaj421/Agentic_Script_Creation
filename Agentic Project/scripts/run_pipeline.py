"""CLI runner: prompt → final MP4.

    python scripts/run_pipeline.py --prompt "A spy meets an informant in Tokyo rain" --scenes 2

Useful for:
  * End-to-end smoke tests (no web UI needed).
  * Scripted demos / CI runs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: F401 — triggers dir setup + env loading
from agents.orchestrator import run_full_pipeline
from shared.schemas import PipelineState
from state_manager import StateManager


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--scenes", type=int, default=2)
    p.add_argument("--style", default="cinematic")
    p.add_argument("--job-id", default=None)
    args = p.parse_args()

    job_id = args.job_id or f"cli_{int(time.time())}"
    state = PipelineState(job_id=job_id, prompt=args.prompt, num_scenes=args.scenes, style=args.style)

    t0 = time.time()
    print(f"▶ starting pipeline job={job_id} prompt={args.prompt!r}")
    state = run_full_pipeline(state)
    dt = time.time() - t0

    print("\n── Pipeline complete ──")
    print(f"  elapsed:   {dt:.1f}s")
    print(f"  job_id:    {job_id}")
    print(f"  title:     {state.story.title}")
    print(f"  scenes:    {len(state.story.scenes)}")
    print(f"  final_mp4: {state.video.final_mp4}")

    print("\n── Saving state manifest ──")
    manifest_path = config.OUTPUTS_DIR / f"{job_id}_state.json"
    manifest_path.write_text(state.model_dump_json(indent=2))
    print(f"  {manifest_path}")

    print("\n── Latest versions ──")
    for v in StateManager().history(job_id):
        print(f"  v{v['version']:3d}  [{v['triggered_by']}]  {v['change_summary']}")


if __name__ == "__main__":
    main()
