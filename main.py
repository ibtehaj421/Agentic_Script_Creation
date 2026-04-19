import asyncio
import json
from graph.workflow import build_graph
from langgraph.types import Command

async def run(input_mode: str, raw_input: str, num_scenes: int = 3):
    graph = build_graph()

    initial_state = {
        "input_mode":        input_mode,
        "raw_input":         raw_input,
        "num_scenes":        num_scenes,
        "script":            {},
        "characters":        [],
        "images":            [],
        "validation_status": "pending",
        "hitl_approved":     False,
        "errors":            [],
        "status":            "started"
    }

    config = {"configurable": {"thread_id": "run-1"}}

    # ── First run — pauses before hitl ──
    print("\n── Running pipeline (will pause at HITL) ──\n")
    async for event in graph.astream(initial_state, config):
        for node in event:
            if node != "__interrupt__":
                print(f"  ✓ {node}")

    # ── Show preview ──
    state = graph.get_state(config)
    script = state.values.get("script", {})
    preview = json.dumps(script, indent=2)[:800]
    print(f"\n── Script Preview ──\n{preview}\n")

    # ── Human decision ──
    approved = input("Approve script? (y/n): ").strip().lower() == "y"

    # ── Resume by passing Command with updated state ──
    print("\n── Resuming pipeline ──\n")
    async for event in graph.astream(
        Command(resume={"approved": approved}),
        config
    ):
        for node in event:
            if node != "__interrupt__":
                print(f"  ✓ {node}")

    final = graph.get_state(config)
    print(f"\n── Done ──")
    print(f"  status:     {final.values.get('status')}")
    print(f"  scenes:     {len(final.values.get('script', {}).get('scenes', []))}")
    print(f"  characters: {len(final.values.get('characters', []))}")
    print(f"  images:     {len(final.values.get('images', []))}")
    print(f"  errors:     {final.values.get('errors')}")

if __name__ == "__main__":
    asyncio.run(run(
        input_mode="auto",
        raw_input="A cyberpunk detective investigates a corporate conspiracy in 2087 Neo-Tokyo",
        num_scenes=3
    ))