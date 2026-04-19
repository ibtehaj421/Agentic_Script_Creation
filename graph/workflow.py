import json
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents.scriptwriter import scriptwriter_agent
from agents.validator import validator_agent
from agents.hitl import hitl_agent
from agents.character_designer import character_designer_agent
from agents.image_synthesizer import image_synthesizer_agent

# ── State ────────────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    input_mode:        Literal["manual", "auto"]
    raw_input:         str
    num_scenes:        int
    script:            dict
    characters:        list
    images:            list
    validation_status: str
    hitl_approved:     bool
    errors:            list
    status:            str

# ── Node wrappers ─────────────────────────────────────────────────────────────

async def mode_selector_node(state: PipelineState) -> dict:
    # nothing to compute — routing happens in the conditional edge
    return {}

async def validator_node(state: PipelineState) -> dict:
    return await validator_agent(state)

async def scriptwriter_node(state: PipelineState) -> dict:
    return await scriptwriter_agent(state)

async def hitl_node(state: PipelineState) -> dict:
    return await hitl_agent(state)

async def character_node(state: PipelineState) -> dict:
    return await character_designer_agent(state)

async def image_node(state: PipelineState) -> dict:
    return await image_synthesizer_agent(state)

async def memory_commit_node(state: PipelineState) -> dict:
    # write final outputs to disk
    import os
    os.makedirs("outputs", exist_ok=True)

    with open("outputs/scene_manifest.json", "w") as f:
        json.dump(state["script"], f, indent=2)

    with open("outputs/character_db.json", "w") as f:
        json.dump(state["characters"], f, indent=2)

    return {"status": "done"}

# ── Routing functions ─────────────────────────────────────────────────────────

def route_by_mode(state: PipelineState) -> str:
    return state["input_mode"]          # "manual" | "auto"

def route_by_validation(state: PipelineState) -> str:
    return state["validation_status"]   # "passed" | "failed"

def route_by_hitl(state: PipelineState) -> str:
    return "approved" if state["hitl_approved"] else "rejected"

# ── Graph assembly ────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(PipelineState)

    # nodes
    graph.add_node("mode_selector",   mode_selector_node)
    graph.add_node("validator",       validator_node)
    graph.add_node("scriptwriter",    scriptwriter_node)
    graph.add_node("hitl",            hitl_node)
    graph.add_node("character",       character_node)
    graph.add_node("image",           image_node)
    graph.add_node("memory_commit",   memory_commit_node)

    # entry
    graph.set_entry_point("mode_selector")

    # mode_selector → validator or scriptwriter
    graph.add_conditional_edges("mode_selector", route_by_mode, {
        "manual": "validator",
        "auto":   "scriptwriter"
    })

    # validator → hitl or END (on failure)
    graph.add_conditional_edges("validator", route_by_validation, {
        "passed": "hitl",
        "failed": END
    })

    # scriptwriter always goes to hitl
    graph.add_edge("scriptwriter", "hitl")

    # hitl → character or END (on rejection)
    graph.add_conditional_edges("hitl", route_by_hitl, {
        "approved": "character",
        "rejected": END
    })

    # linear from character onwards
    graph.add_edge("character",     "image")
    graph.add_edge("image",         "memory_commit")
    graph.add_edge("memory_commit", END)

    # MemorySaver enables interrupt/resume for HITL
    checkpointer = MemorySaver()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl"]      # pause before hitl_node executes
    )