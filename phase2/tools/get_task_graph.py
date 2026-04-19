import json
import os
from config import LOGS_DIR

def get_task_graph(scene_manifest: dict) -> list[dict]:
    """Decomposes scene_manifest into independent executable task units."""
    tasks = []
    for scene in scene_manifest.get("scenes", []):
        tasks.append({
            "scene_id": scene["scene_id"],
            "location": scene["location"],
            "characters": scene["characters"],
            "dialogue": scene["dialogue"],
            "action": scene["action"]
        })
    
    # Use config path for logs
    log_path = os.path.join(LOGS_DIR, "task_graph_logs.json")
    with open(log_path, "w") as f:
        json.dump(tasks, f, indent=2)
        
    return tasks