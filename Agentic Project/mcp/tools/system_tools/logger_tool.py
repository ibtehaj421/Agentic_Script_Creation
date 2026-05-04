"""Emit a structured event into the pipeline event stream."""
from __future__ import annotations

from typing import Any

from mcp.base_tool import BaseTool, ToolSpec
from shared.utils import emit


class EventLogTool(BaseTool):
    spec = ToolSpec(
        name="event_log",
        description="Emit a structured event to the job's event stream (seen by the web UI).",
        category="system",
    )

    def run(self, job_id: str, phase: str, event: str, data: dict[str, Any] | None = None) -> bool:
        emit(job_id, phase, event, data or {})
        return True
