"""Executor that looks up a tool by name and invokes it.

Separate from `ToolRegistry` so we can wrap every call with retry +
logging + event emission without touching the registry internals.
"""
from __future__ import annotations

import inspect
import time
from typing import Any, Optional

from shared.utils import emit, get_logger

from .tool_registry import registry


def _tool_accepts(tool: Any, kwarg: str) -> bool:
    """Return True iff `tool.run(...)` declares `kwarg` (or **kwargs)."""
    try:
        sig = inspect.signature(tool.run)
    except (TypeError, ValueError):
        return False
    for p in sig.parameters.values():
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if p.name == kwarg:
            return True
    return False


class ToolExecutor:
    def __init__(self, max_retries: int = 2, job_id: Optional[str] = None) -> None:
        self.max_retries = max_retries
        self.job_id = job_id or "no-job"
        self.log = get_logger("mcp.executor")

    def execute(self, tool_name: str, **kwargs: Any) -> Any:
        tool = registry.get(tool_name)
        # Auto-inject job_id so every tool can route its outputs into a
        # per-job subdirectory and we never get cross-job filename
        # collisions. Only inject when the tool actually declares the
        # parameter (or accepts **kwargs); LLM tools like generate_story
        # don't, and would error on an unexpected keyword.
        if (
            "job_id" not in kwargs
            and self.job_id
            and self.job_id != "no-job"
            and _tool_accepts(tool, "job_id")
        ):
            kwargs["job_id"] = self.job_id
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                emit(self.job_id, tool.spec.category, "tool_start", {"tool": tool_name, "attempt": attempt})
                t0 = time.time()
                result = tool.run(**kwargs)
                dt_ms = int((time.time() - t0) * 1000)
                emit(self.job_id, tool.spec.category, "tool_ok", {"tool": tool_name, "dt_ms": dt_ms})
                return result
            except Exception as e:
                last_err = e
                self.log.warning(f"{tool_name} attempt {attempt} failed: {e}")
                emit(self.job_id, tool.spec.category, "tool_retry", {"tool": tool_name, "err": str(e)})
                time.sleep(0.5 * (attempt + 1))
        emit(self.job_id, tool.spec.category, "tool_fail", {"tool": tool_name, "err": str(last_err)})
        raise RuntimeError(f"Tool {tool_name!r} failed after {self.max_retries + 1} attempts: {last_err}")


def execute(tool_name: str, job_id: Optional[str] = None, **kwargs: Any) -> Any:
    """Convenience one-shot executor."""
    return ToolExecutor(job_id=job_id).execute(tool_name, **kwargs)
