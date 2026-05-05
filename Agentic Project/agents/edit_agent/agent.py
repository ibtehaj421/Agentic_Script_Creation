"""LangGraph-wrapped edit agent with SqliteSaver checkpointer.

Graph:
    [classify_intent] → [plan] → [execute] → [snapshot] → END

The checkpointer persists per-thread state across turns so multi-turn
edits ("change voice to whispered"... "also on scene 2") remain coherent.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from config import DATA_DIR
from shared.schemas import EditIntent, EditResult, PipelineState
from shared.utils import emit
from state_manager import StateManager

from .executor import execute_edit
from .intent_classifier import classify_intent
from .planner import plan_execution


class EditGraphState(TypedDict, total=False):
    job_id: str
    query: str
    pipeline_state: dict          # serialised PipelineState
    intent: dict                  # serialised EditIntent
    plan: list                    # list of (step_name, kwargs) tuples
    result: dict                  # serialised EditResult


def _classify_node(state: EditGraphState) -> EditGraphState:
    ps = PipelineState(**state["pipeline_state"])
    intent = classify_intent(state["query"], state=ps, job_id=state["job_id"])
    emit(state["job_id"], "edit", "intent_classified", intent.model_dump())
    return {"intent": intent.model_dump()}


def _plan_node(state: EditGraphState) -> EditGraphState:
    ps = PipelineState(**state["pipeline_state"])
    intent = EditIntent(**state["intent"])
    plan = plan_execution(intent, ps)
    emit(state["job_id"], "edit", "plan_built", {"steps": [s for s, _ in plan]})
    return {"plan": plan}


def _execute_node(state: EditGraphState) -> EditGraphState:
    ps = PipelineState(**state["pipeline_state"])
    ps = execute_edit(state["plan"], ps, job_id=state["job_id"])
    return {"pipeline_state": ps.model_dump(mode="json")}


def _snapshot_node(state: EditGraphState) -> EditGraphState:
    ps = PipelineState(**state["pipeline_state"])
    intent = EditIntent(**state["intent"])
    mgr = StateManager()
    snap = mgr.snapshot(
        ps,
        changed_phase=intent.target.value,
        change_summary=f"{intent.intent} ({intent.scope}) from: {intent.raw_query[:80]}",
        triggered_by="edit",
    )
    ps.version = snap.version
    affected = _affected_scenes(intent)
    result = EditResult(
        ok=True,
        intent=intent,
        new_version=snap.version,
        message=f"Applied {intent.intent}. New version v{snap.version}.",
        affected_scenes=affected,
    )
    emit(state["job_id"], "edit", "applied", result.model_dump())
    return {
        "pipeline_state": ps.model_dump(mode="json"),
        "result": result.model_dump(),
    }


def _affected_scenes(intent: EditIntent) -> list[int]:
    if intent.scope.startswith("scene:"):
        try:
            return [int(intent.scope.split(":", 1)[1])]
        except ValueError:
            return []
    return []


def _build_graph(persist: bool = True):
    """Build the edit-agent graph. `persist` is accepted for API symmetry with
    the original SqliteSaver design, but we currently use the in-memory saver;
    state persistence across processes is handled by the StateManager's
    SQLite log, not the LangGraph checkpointer."""
    g = StateGraph(EditGraphState)
    g.add_node("classify", _classify_node)
    g.add_node("plan", _plan_node)
    g.add_node("execute", _execute_node)
    g.add_node("snapshot", _snapshot_node)
    g.set_entry_point("classify")
    g.add_edge("classify", "plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "snapshot")
    g.add_edge("snapshot", END)
    return g.compile(checkpointer=MemorySaver())


class EditAgent:
    """Wrapper that holds the LangGraph app and a thread-id cache."""

    def __init__(self, persist: bool = False) -> None:
        # Use MemorySaver by default — SqliteSaver has nuanced context-manager
        # semantics across langgraph versions and we don't strictly need
        # cross-process persistence for the demo.
        self.app = _build_graph(persist=persist)

    def run(self, query: str, state: PipelineState, thread_id: Optional[str] = None) -> EditResult:
        thread = thread_id or state.job_id
        result_state = self.app.invoke(
            {
                "job_id": state.job_id,
                "query": query,
                "pipeline_state": state.model_dump(mode="json"),
            },
            config={"configurable": {"thread_id": thread}},
        )
        return EditResult(**result_state["result"]), PipelineState(**result_state["pipeline_state"])


def run_edit_once(query: str, state: PipelineState) -> tuple[EditResult, PipelineState]:
    """Convenience: fresh graph, one-shot edit."""
    return EditAgent(persist=False).run(query, state)
