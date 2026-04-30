from .ffmpeg_tool import KenBurnsTool, PortraitOverlayTool, SpeedAdjustTool
from .compositor_tool import SceneComposeTool, FinalCompositorTool
from .subtitle_tool import SubtitleBurnTool
from .color_grade_tool import VideoColorGradeTool

from mcp.tool_registry import registry

registry.register(KenBurnsTool())
registry.register(PortraitOverlayTool())
registry.register(SpeedAdjustTool())
registry.register(SceneComposeTool())
registry.register(FinalCompositorTool())
registry.register(SubtitleBurnTool())
registry.register(VideoColorGradeTool())
