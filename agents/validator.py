"""Script Validator Agent.

Role:   Ensures correctness of manually provided scripts.
Tools:  validate_script, commit_memory (discovered via MCP).

Accepts either:
    * Free-form screenplay text (SCENE/INT./EXT. headers, SPEAKER: lines), or
    * A pre-structured JSON manifest with a `scenes` array.
"""
from __future__ import annotations

import json
from typing import Any

from .mcp_client import call_tool


def _structured_check(script_obj: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    scenes = script_obj.get("scenes", [])
    if not scenes:
        errors.append("No scenes found")
    for i, scene in enumerate(scenes, start=1):
        for field in ("location", "characters", "dialogue", "action"):
            if field not in scene:
                errors.append(f"Scene {i}: missing {field}")
        for turn in scene.get("dialogue", []):
            if "speaker" not in turn:
                errors.append(f"Scene {i}: dialogue missing speaker")
            if "line" not in turn:
                errors.append(f"Scene {i}: dialogue missing line")
    return errors, {"scenes": scenes}


async def validator_agent(state: dict[str, Any]) -> dict[str, Any]:
    raw_script = state.get("raw_input", "")

    # Try JSON-structured path first
    try:
        parsed = json.loads(raw_script)
        if isinstance(parsed, dict) and "scenes" in parsed:
            errors, script = _structured_check(parsed)
            passed = not errors
        else:
            raise ValueError("not a scene manifest")
    except (json.JSONDecodeError, ValueError):
        raw = await call_tool("validate_script", script_text=raw_script)
        result = json.loads(raw)
        script = {"scenes": result.get("scenes", [])}
        errors = result.get("errors", [])
        passed = bool(result.get("ok"))

    if passed:
        await call_tool(
            "commit_memory",
            key="script:latest",
            content=json.dumps(script),
            kind="script",
        )

    log = state.get("log", []) + [f"[validator] passed={passed}"]
    return {
        "validation_status": "passed" if passed else "failed",
        "script": script if passed else {},
        "errors": errors,
        "log": log,
    }
