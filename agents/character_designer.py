"""Character Designer Agent.

Role:   Extracts and formalises character identities from the script.
Tools:  design_characters, query_stock_footage, commit_memory.

Each character record is enriched with a stock-footage reference so the
downstream video agent has a pointer to style/motion references.
"""
from __future__ import annotations

import json
from typing import Any

from .mcp_client import call_tool


def _normalise(char: dict[str, Any]) -> dict[str, Any]:
    """Normalise character record to the schema the rest of the pipeline
    expects (phase2 reads personality_traits / appearance / reference_style)."""
    out = dict(char)
    if "traits" in out and "personality_traits" not in out:
        out["personality_traits"] = out.pop("traits")
    # appearance may come back as a list or a string — keep both forms.
    appearance = out.get("appearance", "")
    if isinstance(appearance, list):
        out["appearance"] = ", ".join(appearance)
    out.setdefault("reference_style", "cinematic")
    return out


async def character_designer_agent(state: dict[str, Any]) -> dict[str, Any]:
    script = state.get("script", {})

    raw = await call_tool(
        "design_characters", scene_manifest_json=json.dumps(script)
    )
    parsed = json.loads(raw)
    chars = [_normalise(c) for c in parsed.get("characters", [])]

    for c in chars:
        ref_raw = await call_tool(
            "query_stock_footage",
            description=str(c.get("appearance", c.get("name", ""))),
        )
        c["stock_refs"] = json.loads(ref_raw).get("results", [])
        await call_tool(
            "commit_memory",
            key=f"character:{c.get('name','unknown')}",
            content=json.dumps(c),
            kind="character",
        )

    log = state.get("log", []) + [f"[character] {len(chars)} identities"]
    return {"characters": chars, "status": "characters_designed", "log": log}
