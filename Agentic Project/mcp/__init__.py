"""Local MCP-style tool abstraction.

Why this layer exists: the spec asks for an MCP tool layer (Section 8 /
Tech Stack) so agents can discover and invoke tools dynamically rather
than hard-importing them. `BaseTool` + `ToolRegistry` + `ToolExecutor`
fulfil that role while still letting us run the whole pipeline in-process
for speed — the real `fastmcp` server in `mcp/server.py` exposes the same
tools over stdio for out-of-process inspection and for the spec's
"MCP tool usage" rubric item.
"""
from .base_tool import BaseTool, ToolSpec
from .tool_registry import ToolRegistry, registry
from .tool_executor import ToolExecutor, execute

__all__ = [
    "BaseTool",
    "ToolSpec",
    "ToolRegistry",
    "registry",
    "ToolExecutor",
    "execute",
]
