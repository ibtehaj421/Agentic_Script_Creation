"""LangGraph workflow for Phase 2 — THE STUDIO FLOOR.

Topology:

    scene_parser ──fan-out──► voice_synth[n]  ──► lip_sync (barrier)
                  └─fan-out──► video_gen[n]   ──► face_swap[n] ──► lip_sync (barrier)

`lip_sync_node` is a single idempotent finaliser. It iterates every
scene that now has both a face-swapped clip and dialogue audio and
produces `raw_scenes/scene_NN.mp4`. Because LangGraph may invoke it
after either branch finishes, the node short-circuits scenes that have
already been committed to the final checkpoint.
"""
from __future__ import annotations

from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from agents.face_swap_agent import face_swap_node
from agents.lip_sync_agent import lip_sync_node
from agents.scene_parser_agent import scene_parser_node
from agents.video_gen_agent import video_gen_node
from agents.voice_synth_agent import voice_synth_node
from state.studio_state import StudioState


def route_to_parallel_branches(state: StudioState):
    sends = []
    for scene in state["task_graph"]:
        sends.append(Send("voice_synth_node", {"scene": scene}))
        sends.append(Send("video_gen_node", {"scene": scene}))
    return sends


def route_to_face_swap(state: StudioState):
    return [
        Send(
            "face_swap_node",
            {"scene": scene, "video_outputs": state["video_outputs"]},
        )
        for scene in state["task_graph"]
    ]


graph = StateGraph(StudioState)

graph.add_node("scene_parser_node", scene_parser_node)
graph.add_node("voice_synth_node", voice_synth_node)
graph.add_node("video_gen_node", video_gen_node)
graph.add_node("face_swap_node", face_swap_node)
graph.add_node("lip_sync_node", lip_sync_node)

graph.set_entry_point("scene_parser_node")
graph.add_conditional_edges("scene_parser_node", route_to_parallel_branches)
graph.add_conditional_edges("video_gen_node", route_to_face_swap)
# Converge both branches at the single lip_sync barrier
graph.add_edge("voice_synth_node", "lip_sync_node")
graph.add_edge("face_swap_node", "lip_sync_node")
graph.add_edge("lip_sync_node", END)

app = graph.compile()
