"""Entry point for Phase 1 — THE WRITER'S ROOM.

Usage:
    python main.py                                    # auto mode, default prompt
    python main.py --mode auto --prompt "..."
    python main.py --mode manual --script path.txt
    python main.py --auto-approve                     # skip HITL prompt (for CI runs)
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from langgraph.types import Command

from graph.workflow import build_graph


async def run(
    input_mode: str,
    raw_input: str,
    num_scenes: int,
    auto_approve: bool,
) -> None:
    graph = build_graph()

    initial = {
        "input_mode": input_mode,
        "raw_input": raw_input,
        "num_scenes": num_scenes,
        "script": {},
        "characters": [],
        "images": [],
        "validation_status": "pending",
        "hitl_approved": False,
        "errors": [],
        "status": "started",
        "log": [],
    }
    config = {"configurable": {"thread_id": "phase1-run"}}

    print("\n── Running pipeline (will pause at HITL) ──\n")
    async for event in graph.astream(initial, config):
        for node in event:
            if node != "__interrupt__":
                print(f"  ✓ {node}")

    state = graph.get_state(config)
    script = state.values.get("script", {})
    if not script.get("scenes"):
        print("\n── No script produced; aborting ──")
        print(json.dumps(state.values.get("errors", []), indent=2))
        return

    preview = json.dumps(script, indent=2)
    print(f"\n── Script Preview ──\n{preview[:800]}\n{'...' if len(preview) > 800 else ''}")

    if auto_approve:
        approved = True
        print("── Auto-approving (non-interactive) ──")
    else:
        approved = input("Approve script? [Y/n] ").strip().lower() in ("", "y", "yes")

    print("\n── Resuming pipeline ──\n")
    async for event in graph.astream(
        Command(resume={"approved": approved}), config
    ):
        for node in event:
            if node != "__interrupt__":
                print(f"  ✓ {node}")

    final = graph.get_state(config).values
    print("\n── Done ──")
    print(f"  status:     {final.get('status')}")
    print(f"  scenes:     {len(final.get('script', {}).get('scenes', []))}")
    print(f"  characters: {len(final.get('characters', []))}")
    print(f"  images:     {len(final.get('images', []))}")
    if final.get("errors"):
        print(f"  errors:     {final.get('errors')}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["auto", "manual"], default="auto")
    p.add_argument(
        "--prompt",
        default="A cyberpunk detective investigates a corporate conspiracy in 2087 Neo-Tokyo",
    )
    p.add_argument("--script", default=None, help="Path to manual script (.txt or .json)")
    p.add_argument("--num-scenes", type=int, default=3)
    p.add_argument("--auto-approve", action="store_true", help="Skip HITL prompt")
    args = p.parse_args()

    raw_input = (
        Path(args.script).read_text() if args.script and args.mode == "manual"
        else args.prompt
    )
    asyncio.run(run(args.mode, raw_input, args.num_scenes, args.auto_approve))


if __name__ == "__main__":
    main()
