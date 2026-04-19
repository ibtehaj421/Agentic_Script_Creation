from state.studio_state import StudioState
from tools.model_wrappers import query_stock_footage
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint

def video_gen_node(payload: dict) -> dict:
    scene = payload["scene"]
    scene_id = scene["scene_id"]
    checkpoint_id = f"video_{scene_id}"
    
    if checkpoint_exists(checkpoint_id):
        raw_video = load_checkpoint(checkpoint_id)
    else:
        visual_cues = " ".join(d["visual_cue"] for d in scene["dialogue"])
        raw_video = query_stock_footage(scene["location"], visual_cues, scene["action"])
        commit_memory(raw_video, checkpoint_id=checkpoint_id)
        
    return {"video_outputs": {f"scene_{scene_id}": raw_video}}