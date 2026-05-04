"""Phase 5 rubric: state versioning + undo round-trip."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.schemas import PipelineState
from state_manager import StateManager


@pytest.fixture
def tmp_state_mgr(tmp_path, monkeypatch):
    # Redirect the state DB + versions dir into pytest's tmp_path
    import config
    monkeypatch.setattr(config, "STATE_DB", tmp_path / "state.sqlite")
    monkeypatch.setattr(config, "STATE_VERSIONS_DIR", tmp_path / "versions")
    monkeypatch.setattr(config, "OUTPUTS_DIR", tmp_path / "outputs")
    (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "versions").mkdir(parents=True, exist_ok=True)

    # state_manager modules cached the paths at import; refresh
    from state_manager import storage, snapshot
    monkeypatch.setattr(storage, "STATE_DB", config.STATE_DB, raising=False)
    monkeypatch.setattr(snapshot, "STATE_VERSIONS_DIR", config.STATE_VERSIONS_DIR, raising=False)
    monkeypatch.setattr(snapshot, "OUTPUTS_DIR", config.OUTPUTS_DIR, raising=False)
    return StateManager()


def test_append_only_history(tmp_state_mgr: StateManager):
    mgr = tmp_state_mgr
    state = PipelineState(job_id="jA", prompt="p", num_scenes=1)
    s1 = mgr.snapshot(state, changed_phase="pipeline", change_summary="init")
    state.story.title = "Second"
    s2 = mgr.snapshot(state, changed_phase="edit", change_summary="after edit")
    history = mgr.history("jA")
    assert [h["version"] for h in history] == [s1.version, s2.version]
    assert s1.version == 1 and s2.version == 2


def test_revert_moves_active_pointer_without_new_row(tmp_state_mgr: StateManager):
    """Undo / restore is a pointer move, not a new edit. The version log
    stays append-only but no redundant `[undo] Reverted to vN` rows."""
    mgr = tmp_state_mgr
    state = PipelineState(job_id="jB", prompt="p", num_scenes=1)
    state.story.title = "v1"
    s1 = mgr.snapshot(state)
    state.story.title = "v2"
    s2 = mgr.snapshot(state)
    assert s2.version == 2
    assert s2.parent_version == 1
    assert mgr.active_version("jB") == 2

    out = mgr.revert("jB", 1)
    assert out["ok"] is True
    assert out["active_version"] == 1
    # No new row inserted — history still has just v1, v2.
    assert [h["version"] for h in mgr.history("jB")] == [1, 2]
    # Active pointer is now v1; latest() reflects that.
    assert mgr.active_version("jB") == 1
    latest = mgr.latest("jB")
    assert latest.story.title == "v1"


def test_branching_after_undo(tmp_state_mgr: StateManager):
    """v1 → v2 → undo to v1 → new edit creates v3 with parent=v1."""
    mgr = tmp_state_mgr
    state = PipelineState(job_id="jBranch", prompt="p", num_scenes=1)
    state.story.title = "v1"
    mgr.snapshot(state)
    state.story.title = "v2"
    mgr.snapshot(state)

    mgr.revert("jBranch", 1)  # active = v1
    assert mgr.active_version("jBranch") == 1

    state.story.title = "v3-from-v1"
    s3 = mgr.snapshot(state)
    assert s3.version == 3
    assert s3.parent_version == 1   # branched from v1, not v2
    assert mgr.active_version("jBranch") == 3

    # Lineage of active (v3) is [3, 1]
    assert mgr.lineage("jBranch") == [3, 1]
    # Lineage of v2 (the abandoned branch) is [2, 1]
    assert mgr.lineage("jBranch", 2) == [2, 1]


def test_asset_freeze_and_restore(tmp_state_mgr: StateManager, tmp_path):
    mgr = tmp_state_mgr
    # Fabricate an output file
    outdir = tmp_path / "outputs" / "video"
    outdir.mkdir(parents=True, exist_ok=True)
    final_mp4 = outdir / "final.mp4"
    final_mp4.write_bytes(b"v1-content")

    state = PipelineState(job_id="jC", prompt="p", num_scenes=1)
    state.video.final_mp4 = str(final_mp4)
    mgr.snapshot(state)

    # Overwrite the file (simulating an edit)
    final_mp4.write_bytes(b"v2-content")
    mgr.snapshot(state)

    # Revert to v1 -> file should be restored
    mgr.revert("jC", 1)
    assert final_mp4.read_bytes() == b"v1-content"
