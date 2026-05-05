from .tts_tool import TTSTool
from .bgm_tool import BGMTool
from .audio_merger import AudioMergerTool

from mcp.tool_registry import registry

registry.register(TTSTool())
registry.register(BGMTool())
registry.register(AudioMergerTool())
