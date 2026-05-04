"""Simple read/write tools. Kept thin — actual path safety lives in
`shared.utils.io_utils.atomic_write_*`."""
from __future__ import annotations

from pathlib import Path

from mcp.base_tool import BaseTool, ToolSpec
from shared.utils import atomic_write_text


class FileReadTool(BaseTool):
    spec = ToolSpec(name="file_read", description="Read a UTF-8 text file.", category="system")

    def run(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")


class FileWriteTool(BaseTool):
    spec = ToolSpec(name="file_write", description="Atomically write a UTF-8 text file.", category="system")

    def run(self, path: str, content: str) -> str:
        atomic_write_text(path, content)
        return path
