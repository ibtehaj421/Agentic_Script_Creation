"""Image Synthesizer Agent.

Role:   Generates reference images for every character record.
Tool:   generate_character_image (discovered via MCP — backed by
        Pollinations, a free and keyless diffusion endpoint).
"""
from __future__ import annotations

from typing import Any

from .mcp_client import call_tool


async def image_synthesizer_agent(state: dict[str, Any]) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    for c in state.get("characters", []):
        path = await call_tool(
            "generate_character_image",
            name=c.get("name", "unknown"),
            appearance=str(c.get("appearance", "")),
            style=c.get("reference_style", "cinematic"),
        )
        images.append({"character": c.get("name"), "path": path})

    log = state.get("log", []) + [f"[image] {len(images)} renders"]
    return {"images": images, "status": "images_generated", "log": log}
