"""Verify intent → plan mapping for each target bucket."""
from agents.edit_agent.planner import plan_execution
from shared.schemas import EditIntent, EditTarget, PipelineState


def _st():
    return PipelineState(job_id="j", prompt="p", num_scenes=2)


def test_plan_audio_change_voice_tone():
    intent = EditIntent(intent="change_voice_tone", target=EditTarget.AUDIO,
                        scope="scene:1", parameters={"tone": "whispered"}, raw_query="")
    steps = plan_execution(intent, _st())
    assert any("audio.regenerate_scene_audio" in s[0] for s in steps)
    assert any("video.rebuild_scene" in s[0] for s in steps)


def test_plan_frame_darker_includes_background_regen():
    intent = EditIntent(intent="make_scene_darker", target=EditTarget.VIDEO_FRAME,
                        scope="scene:2", parameters={"brightness": 0.5}, raw_query="")
    steps = plan_execution(intent, _st())
    assert any("video.regenerate_scene_background" in s[0] for s in steps)


def test_plan_video_speed_change():
    intent = EditIntent(intent="speed_up_scene", target=EditTarget.VIDEO,
                        scope="scene:1", parameters={"speed": 1.5}, raw_query="")
    steps = plan_execution(intent, _st())
    assert steps and steps[0][0] == "video.adjust_scene_speed"


def test_plan_remove_subtitle_toggles_burn():
    intent = EditIntent(intent="remove_subtitle", target=EditTarget.VIDEO,
                        scope="global", parameters={"burn": False}, raw_query="")
    steps = plan_execution(intent, _st())
    assert steps[0][0] == "video.burn_subtitles_toggle"
    assert steps[0][1]["burn"] is False


def test_plan_script_cascades_all_phases():
    intent = EditIntent(intent="regenerate_script", target=EditTarget.SCRIPT,
                        scope="global", parameters={}, raw_query="")
    steps = plan_execution(intent, _st())
    names = [s[0] for s in steps]
    assert "story.rerun" in names and "audio.rerun" in names and "video.rerun" in names
