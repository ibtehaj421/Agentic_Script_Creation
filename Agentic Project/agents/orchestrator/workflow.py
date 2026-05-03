"""Top-level LangGraph orchestrating the full prompt → final MP4 pipeline.

    START → story → audio → video → snapshot → END

Each node serialises the mutated PipelineState back into the graph state
so the checkpointer can roll back if a downstream node fails.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

# Trigger MCP tool self-registration (idempotent). Any entry point the user
# hits — CLI, FastAPI, test — ultimately imports this module, so it's a
# reliable single place to ensure the registry is populated.
import mcp.tools  # noqa: F401

from agents.audio_agent import run_audio_phase
from agents.story_agent import run_story_phase
from agents.video_agent import run_video_phase
from shared.schemas import PipelineState
from shared.utils import emit
from state_manager import StateManager

from .state import OrchState


def _story_node(state: OrchState) -> OrchState:
    ps = PipelineState(**state["pipeline_state"])
    ps = run_story_phase(ps, job_id=state["job_id"])
    return {"pipeline_state": ps.model_dump(mode="json")}


def _audio_node(state: OrchState) -> OrchState:
    ps = PipelineState(**state["pipeline_state"])
    ps = run_audio_phase(ps, job_id=state["job_id"])
    return {"pipeline_state": ps.model_dump(mode="json")}


def _video_node(state: OrchState) -> OrchState:
    ps = PipelineState(**state["pipeline_state"])
    ps = run_video_phase(ps, job_id=state["job_id"])
    return {"pipeline_state": ps.model_dump(mode="json")}


def _snapshot_node(state: OrchState) -> OrchState:
    ps = PipelineState(**state["pipeline_state"])
    mgr = StateManager()
    snap = mgr.snapshot(ps, changed_phase="pipeline", change_summary="Initial generation", triggered_by="pipeline")
    ps.version = snap.version
    emit(state["job_id"], "pipeline", "snapshot", {"version": snap.version})
    return {"pipeline_state": ps.model_dump(mode="json")}


def build_orchestrator():
    g = StateGraph(OrchState)
    g.add_node("story", _story_node)
    g.add_node("audio", _audio_node)
    g.add_node("video", _video_node)
    g.add_node("snapshot", _snapshot_node)
    g.set_entry_point("story")
    g.add_edge("story", "audio")
    g.add_edge("audio", "video")
    g.add_edge("video", "snapshot")
    g.add_edge("snapshot", END)
    return g.compile(checkpointer=MemorySaver())


def run_full_pipeline(state: PipelineState) -> PipelineState:
    """Invoke the orchestrator end-to-end. Returns the final PipelineState."""
    app = build_orchestrator()
    out = app.invoke(
        {"job_id": state.job_id, "pipeline_state": state.model_dump(mode="json")},
        config={"configurable": {"thread_id": state.job_id}},
    )
    return PipelineState(**out["pipeline_state"])
