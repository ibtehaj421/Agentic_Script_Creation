"""Thread-safe tool registry.

Tools self-register on import (see `mcp/tools/__init__.py`). The registry
is how agents discover what's available without import-time coupling.
"""
from __future__ import annotations

from threading import RLock
from typing import Dict, Iterable, List

from .base_tool import BaseTool, ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._lock = RLock()

    def register(self, tool: BaseTool) -> None:
        with self._lock:
            if tool.spec.name in self._tools:
                # Idempotent re-register is fine (hot reload, test fixtures)
                return
            self._tools[tool.spec.name] = tool

    def get(self, name: str) -> BaseTool:
        with self._lock:
            if name not in self._tools:
                raise KeyError(f"Tool {name!r} not registered. Have: {list(self._tools)}")
            return self._tools[name]

    def by_category(self, category: str) -> List[BaseTool]:
        with self._lock:
            return [t for t in self._tools.values() if t.spec.category == category]

    def list_specs(self) -> List[ToolSpec]:
        with self._lock:
            return [t.spec for t in self._tools.values()]

    def names(self) -> Iterable[str]:
        with self._lock:
            return list(self._tools.keys())


registry = ToolRegistry()
