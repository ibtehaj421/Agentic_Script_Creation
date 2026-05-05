"""MCP Layer rubric item: tools self-register, are callable via the executor."""
from mcp.tool_registry import registry
from mcp.base_tool import BaseTool


EXPECTED = {
    # llm
    "generate_story", "design_characters", "classify_edit_intent", "validate_json_schema",
    # vision
    "generate_character_portrait", "generate_scene_background", "adjust_image_color", "apply_style_filter",
    # audio
    "tts_synthesize", "generate_bgm", "merge_audio",
    # video
    "ken_burns", "overlay_portrait", "adjust_speed",
    "compose_scene", "compose_final", "burn_subtitles",
    # system
    "file_read", "file_write", "state_snapshot", "state_revert", "event_log",
}


def test_all_expected_tools_registered():
    names = set(registry.names())
    missing = EXPECTED - names
    assert not missing, f"missing tools: {missing}"


def test_each_tool_has_spec_and_run():
    for name in registry.names():
        tool = registry.get(name)
        assert isinstance(tool, BaseTool)
        assert tool.spec.name == name
        assert tool.spec.description
        assert callable(tool.run)


def test_category_coverage():
    categories = {registry.get(n).spec.category for n in registry.names()}
    assert {"llm", "vision", "audio", "video", "system"} <= categories
