"""Phase 1 / Integration rubric: shared JSON schema is consumable everywhere."""
from shared.schemas import (
    AudioSegment, Character, DialogueTurn, EditIntent, EditTarget,
    PipelineState, Scene, StoryState, TimingManifest, VideoOutput, VersionSnapshot,
)


def test_pipeline_state_roundtrips():
    s = PipelineState(job_id="x", prompt="hi", num_scenes=2)
    s.story.title = "T"
    s.story.scenes.append(Scene(scene_id=1, location="x", action="y"))
    dumped = s.model_dump_json()
    hydrated = PipelineState.model_validate_json(dumped)
    assert hydrated.story.title == "T"
    assert hydrated.story.scenes[0].scene_id == 1


def test_edit_intent_targets():
    # Ensures the Enum covers the 4 documented targets
    assert {t.value for t in EditTarget} == {"audio", "video_frame", "video", "script"}


def test_dialogue_turn_defaults():
    d = DialogueTurn(speaker="X", line="Hello")
    assert d.emotion == "neutral"
    assert d.visual_cue == ""


def test_timing_manifest_shape():
    tm = TimingManifest()
    tm.segments.append(AudioSegment(scene_id=1, speaker="A", line="hi", audio_file="/tmp/a.wav"))
    assert tm.segments[0].scene_id == 1
    tm.scene_audio[1] = "/tmp/scene.wav"
    assert tm.scene_audio[1].endswith(".wav")


def test_version_snapshot_fields():
    snap = VersionSnapshot(version=1, job_id="j", timestamp_ms=0, state_json="{}", asset_dir="/tmp")
    assert snap.triggered_by == "pipeline"
