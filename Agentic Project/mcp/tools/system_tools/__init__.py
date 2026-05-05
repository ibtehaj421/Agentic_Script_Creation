from .file_tool import FileReadTool, FileWriteTool
from .state_tool import StateSnapshotTool, StateRevertTool
from .logger_tool import EventLogTool

from mcp.tool_registry import registry

registry.register(FileReadTool())
registry.register(FileWriteTool())
registry.register(StateSnapshotTool())
registry.register(StateRevertTool())
registry.register(EventLogTool())
