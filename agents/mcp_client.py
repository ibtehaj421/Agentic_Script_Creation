"""MCP client bootstrap for the Phase 1 agents.

All worker tools are reached through this module. Tools are discovered
dynamically at runtime — no agent imports a concrete tool function,
satisfying the "no hardcoded APIs" constraint in the Phase 1 spec.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "writers_room": {
                "command": sys.executable,
                "args": [str(ROOT / "mcp-servers" / "writers_room_server.py")],
                "transport": "stdio",
            }
        }
    )


_tool_cache: list[Any] | None = None


async def discover_tools() -> list[Any]:
    """Fetch the live tool list from the MCP server (cached)."""
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = await _client().get_tools()
    return _tool_cache


async def call_tool(tool_name: str, **kwargs) -> str:
    """Invoke an MCP-discovered tool by name with structured args."""
    tools = await discover_tools()
    by_name = {t.name: t for t in tools}
    if tool_name not in by_name:
        raise KeyError(
            f"MCP tool {tool_name!r} not found. Available: {list(by_name)}"
        )
    result = await by_name[tool_name].ainvoke(kwargs)
    if isinstance(result, list):
        parts = []
        for item in result:
            parts.append(
                getattr(item, "text", None)
                or (item.get("text") if isinstance(item, dict) else str(item))
            )
        return "".join(p for p in parts if p)
    return result
