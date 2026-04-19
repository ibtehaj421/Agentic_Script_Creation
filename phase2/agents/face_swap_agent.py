from pkg_resources import safe_name

from state.studio_state import StudioState
from tools.identity_validator import identity_validator
from tools.face_swapper import face_swapper
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint
import os

def get_dynamic_image_path(character_name: str) -> str:
    """Dynamically resolves the image path from Phase 1 output."""
    
    safe_name = character_name.title().replace(" ", "_")
    return os.path.join("phase1", "outputs", "characters", f"{safe_name}.png")

def face_swap_node(payload: dict) -> dict:
    scene = payload["scene"]
    video_outputs = payload["video_outputs"]
    scene_id = scene["scene_id"]
    checkpoint_id = f"faceswap_{scene_id}"
    
    if checkpoint_exists(checkpoint_id):
        return {"face_swapped_outputs": {f"scene_{scene_id}": load_checkpoint(checkpoint_id)}}
    
    raw_video = video_outputs.get(f"scene_{scene_id}")
    if not raw_video: return {}
    
    primary_char = scene["characters"][0]
    char_image = get_dynamic_image_path(primary_char)
    
    if identity_validator(primary_char, char_image):
        swapped = face_swapper(char_image, raw_video)
        commit_memory(swapped, checkpoint_id=checkpoint_id)
        return {"face_swapped_outputs": {f"scene_{scene_id}": swapped}}
    else:
        return {"errors": [f"Identity validation failed for scene {scene_id}. Image missing at: {char_image}"]}