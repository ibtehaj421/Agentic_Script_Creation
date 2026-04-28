"""Abstract base class every MCP tool must extend."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ToolSpec:
    name: str
    description: str
    category: str = "generic"     # llm | audio | vision | video | system
    schema: Dict[str, Any] = field(default_factory=dict)  # JSON schema for args


class BaseTool(abc.ABC):
    """All MCP tools implement this interface. Sync is fine — the heavy
    work happens in blocking APIs (ffmpeg, httpx) so there's no win from
    making these async at this layer."""

    spec: ToolSpec

    @abc.abstractmethod
    def run(self, **kwargs: Any) -> Any:
        ...

    # Syntactic sugar so callers can `tool(**kwargs)` without knowing `run`.
    def __call__(self, **kwargs: Any) -> Any:
        return self.run(**kwargs)
