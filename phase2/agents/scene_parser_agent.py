from state.studio_state import StudioState
from tools.get_task_graph import get_task_graph
from tools.commit_memory import commit_memory

def scene_parser_node(state: StudioState) -> StudioState:
    manifest = state["scene_manifest"]
    task_graph = get_task_graph(manifest)
    state["task_graph"] = task_graph
    commit_memory(task_graph, checkpoint_id="task_graph")
    return state