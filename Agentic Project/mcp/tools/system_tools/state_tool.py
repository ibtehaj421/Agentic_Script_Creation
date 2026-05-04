"""Lightweight wrappers so agents can call the state manager through the
MCP abstraction instead of importing it directly. Keeps the "all tools
discoverable via MCP" invariant true."""
from __future__ import annotations

from typing import Any

from mcp.base_tool import BaseTool, ToolSpec


class StateSnapshotTool(BaseTool):
    spec = ToolSpec(
        name="state_snapshot",
        description="Persist a new state version and freeze the referenced assets.",
        category="system",
    )

    def run(self, state: dict[str, Any], changed_phase: str = "", change_summary: str = "", triggered_by: str = "pipeline") -> dict:
        # Lazy import avoids a circular dependency at module load time.
        from state_manager.state_manager import StateManager

        mgr = StateManager()
        snap = mgr.snapshot(state, changed_phase=changed_phase, change_summary=change_summary, triggered_by=triggered_by)
        return snap.model_dump()


class StateRevertTool(BaseTool):
    spec = ToolSpec(
        name="state_revert",
        description="Revert state and assets to a prior version.",
        category="system",
    )

    def run(self, version: int) -> dict[str, Any]:
        from state_manager.state_manager import StateManager

        mgr = StateManager()
        return mgr.revert(version)
