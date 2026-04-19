import json
import os
from config import CHECKPOINT_DIR

def commit_memory(data, checkpoint_id: str):
    """MCP Tool: Persist intermediate output. Supports resumability."""
    path = f"{CHECKPOINT_DIR}/{checkpoint_id}.json"
    with open(path, "w") as f:
        json.dump({"checkpoint_id": checkpoint_id, "data": data}, f)
    return path

def checkpoint_exists(checkpoint_id: str) -> bool:
    return os.path.exists(f"{CHECKPOINT_DIR}/{checkpoint_id}.json")

def load_checkpoint(checkpoint_id: str):
    with open(f"{CHECKPOINT_DIR}/{checkpoint_id}.json") as f:
        return json.load(f)["data"]