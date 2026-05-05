from .image_gen_tool import CharacterPortraitTool, SceneBackgroundTool
from .image_edit_tool import ImageColorAdjustTool
from .style_transfer import StyleOverlayTool

from mcp.tool_registry import registry

registry.register(CharacterPortraitTool())
registry.register(SceneBackgroundTool())
registry.register(ImageColorAdjustTool())
registry.register(StyleOverlayTool())
