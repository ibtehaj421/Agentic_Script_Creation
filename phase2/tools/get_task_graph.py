"""Decompose a scene manifest into independent, parallelisable tasks."""
from __future__ import annotations

import json
import os

from config import LOGS_DIR


def get_task_graph(scene_manifest: dict) -> list[dict]:
    tasks = []
    for scene in scene_manifest.get("scenes", []):
        tasks.append(
            {
                "scene_id": scene["scene_id"],
                "location": scene.get("location", ""),
                "characters": scene.get("characters", []),
                "dialogue": scene.get("dialogue", []),
                "action": scene.get("action", ""),
            }
        )

    log_path = os.path.join(LOGS_DIR, "task_graph_logs.json")
    with open(log_path, "w") as f:
        json.dump(tasks, f, indent=2)

    return tasks
