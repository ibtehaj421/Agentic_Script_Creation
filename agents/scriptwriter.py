"""Scriptwriter Agent.

Role:   Transform abstract prompts into structured, production-ready scripts.
Tools:  generate_script_segment, commit_memory (discovered via MCP).

Reasoning loop:
    1. Read the user prompt from shared state.
    2. Invoke generate_script_segment to decompose it into scenes.
    3. Persist the draft via commit_memory for downstream agents.
"""
from __future__ import annotations

import json
from typing import Any

from .mcp_client import call_tool


async def scriptwriter_agent(state: dict[str, Any]) -> dict[str, Any]:
    prompt = state.get("raw_input", "")
    num_scenes = state.get("num_scenes", 3)

    raw = await call_tool(
        "generate_script_segment", prompt=prompt, num_scenes=num_scenes
    )
    script = json.loads(raw)

    await call_tool(
        "commit_memory",
        key="script:latest",
        content=json.dumps(script),
        kind="script",
    )

    log = state.get("log", []) + [
        f"[scriptwriter] {len(script.get('scenes', []))} scenes"
    ]
    return {"script": script, "status": "script_drafted", "log": log}
