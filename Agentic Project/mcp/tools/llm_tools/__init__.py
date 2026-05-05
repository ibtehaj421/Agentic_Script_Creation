from .text_generator import StoryGeneratorTool, CharacterDesignerTool, EditIntentTool
from .json_structurer import JsonStructurerTool
from mcp.tool_registry import registry

registry.register(StoryGeneratorTool())
registry.register(CharacterDesignerTool())
registry.register(EditIntentTool())
registry.register(JsonStructurerTool())
