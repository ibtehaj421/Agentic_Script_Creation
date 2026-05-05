"""Optional stdio-based MCP server.

Exposes every registered tool over the MCP protocol so Phase 4's demo
can show tool discovery via `python -m mcp inspector -- python mcp/server.py`.
The in-process pipeline uses the local registry directly for speed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402 — provided by `mcp` pkg

from mcp.tool_registry import registry  # noqa: E402
import mcp.tools  # noqa: F401,E402 — triggers self-registration

srv = FastMCP("agentic-video-pipeline")


# Register every tool from the in-process registry as an MCP tool.
def _register_all() -> None:
    for tool in [registry.get(name) for name in list(registry.names())]:
        spec = tool.spec

        # Create a closure per tool so the name binds correctly.
        def _make_fn(t=tool):
            def _fn(**kwargs):
                return t.run(**kwargs)
            _fn.__name__ = t.spec.name
            _fn.__doc__ = t.spec.description
            return _fn

        srv.tool(name=spec.name, description=spec.description)(_make_fn())


_register_all()


if __name__ == "__main__":
    srv.run(transport="stdio")
