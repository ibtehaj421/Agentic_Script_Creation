from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from state.studio_state import StudioState
from agents.scene_parser_agent import scene_parser_node
from agents.voice_synth_agent import voice_synth_node
from agents.video_gen_agent import video_gen_node
from agents.face_swap_agent import face_swap_node
from agents.lip_sync_agent import lip_sync_node

def route_to_parallel_branches(state: StudioState):
    sends = []
    for scene in state["task_graph"]:
        sends.append(Send("voice_synth_node", {"scene": scene}))
        sends.append(Send("video_gen_node", {"scene": scene}))
    return sends

def route_to_face_swap(state: StudioState):
    return [
        Send("face_swap_node", {
            "scene": scene, 
            "video_outputs": state["video_outputs"] # Pass the specific state data needed
        }) 
        for scene in state["task_graph"]
    ]

def route_to_lip_sync(state: StudioState):
    return [
        Send("lip_sync_node", {
            "scene": scene,
            "audio_outputs": state["audio_outputs"],
            "face_swapped_outputs": state["face_swapped_outputs"]
        }) 
        for scene in state["task_graph"]
    ]
graph = StateGraph(StudioState)

graph.add_node("scene_parser_node", scene_parser_node)
graph.add_node("voice_synth_node",  voice_synth_node)
graph.add_node("video_gen_node",    video_gen_node)
graph.add_node("face_swap_node",    face_swap_node)
graph.add_node("lip_sync_node",     lip_sync_node)

graph.set_entry_point("scene_parser_node")
graph.add_conditional_edges("scene_parser_node", route_to_parallel_branches)
graph.add_conditional_edges("video_gen_node",    route_to_face_swap)
graph.add_conditional_edges("face_swap_node",    route_to_lip_sync)
graph.add_conditional_edges("voice_synth_node",  route_to_lip_sync)
graph.add_edge("lip_sync_node", END)

app = graph.compile()