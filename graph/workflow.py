"""LangGraph StateGraph wiring for Phase 1 — THE WRITER'S ROOM.

Supervisor-Worker hierarchical model; the supervisor is implicit in the
routing functions below.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.character_designer import character_designer_agent
from agents.hitl import hitl_agent
from agents.image_synthesizer import image_synthesizer_agent
from agents.mcp_client import call_tool
from agents.scriptwriter import scriptwriter_agent
from agents.state import PipelineState
from agents.validator import validator_agent
from config import OUTPUT_DIR


async def mode_selector_node(state: PipelineState) -> dict[str, Any]:
    mode = state.get("input_mode", "auto")
    log = state.get("log", []) + [f"[mode_selector] mode={mode}"]
    return {"status": f"mode={mode}", "log": log}


async def validator_node(state: PipelineState) -> dict[str, Any]:
    return await validator_agent(state)


async def scriptwriter_node(state: PipelineState) -> dict[str, Any]:
    return await scriptwriter_agent(state)


async def hitl_node(state: PipelineState) -> dict[str, Any]:
    return await hitl_agent(state)


async def character_node(state: PipelineState) -> dict[str, Any]:
    return await character_designer_agent(state)


async def image_node(state: PipelineState) -> dict[str, Any]:
    return await image_synthesizer_agent(state)


async def memory_commit_node(state: PipelineState) -> dict[str, Any]:
    """Persist final artefacts to disk and to the shared ChromaDB."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    script = state.get("script", {})
    characters = state.get("characters", [])

    (OUTPUT_DIR / "scene_manifest.json").write_text(json.dumps(script, indent=2))
    (OUTPUT_DIR / "character_db.json").write_text(json.dumps(characters, indent=2))
    (OUTPUT_DIR / "run_log.json").write_text(
        json.dumps(
            {
                "status": state.get("status"),
                "log": state.get("log", []),
                "images": state.get("images", []),
                "errors": state.get("errors", []),
            },
            indent=2,
        )
    )

    await call_tool(
        "commit_memory",
        key="run:final",
        content=json.dumps(
            {
                "script": script,
                "characters": characters,
                "images": state.get("images", []),
            }
        ),
        kind="run",
    )

    log = state.get("log", []) + ["[memory_commit] run persisted"]
    return {"status": "done", "log": log}


def route_by_mode(state: PipelineState) -> str:
    return state.get("input_mode", "auto")


def route_by_validation(state: PipelineState) -> str:
    return state.get("validation_status", "failed")


def route_by_hitl(state: PipelineState) -> str:
    return "approved" if state.get("hitl_approved") else "rejected"


def build_graph(interrupt_hitl: bool = True):
    g = StateGraph(PipelineState)

    g.add_node("mode_selector", mode_selector_node)
    g.add_node("validator", validator_node)
    g.add_node("scriptwriter", scriptwriter_node)
    g.add_node("hitl", hitl_node)
    g.add_node("character", character_node)
    g.add_node("image", image_node)
    g.add_node("memory_commit", memory_commit_node)

    g.set_entry_point("mode_selector")
    g.add_conditional_edges(
        "mode_selector",
        route_by_mode,
        {"manual": "validator", "auto": "scriptwriter"},
    )
    g.add_conditional_edges(
        "validator",
        route_by_validation,
        {"passed": "hitl", "failed": END},
    )
    g.add_edge("scriptwriter", "hitl")
    g.add_conditional_edges(
        "hitl",
        route_by_hitl,
        {"approved": "character", "rejected": END},
    )
    g.add_edge("character", "image")
    g.add_edge("image", "memory_commit")
    g.add_edge("memory_commit", END)

    return g.compile(checkpointer=MemorySaver())
