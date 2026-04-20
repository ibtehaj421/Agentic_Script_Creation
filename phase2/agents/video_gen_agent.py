"""Video Generation Agent.

Role:   Generates base video for a scene from character references,
        location, visual cues and action text.
Tool:   query_stock_footage (free, keyless — see tools/query_stock_footage.py).
"""
from __future__ import annotations

from tools.commit_memory import checkpoint_exists, commit_memory, load_checkpoint
from tools.query_stock_footage import query_stock_footage
from config import resolve_character_image


def video_gen_node(payload: dict) -> dict:
    scene = payload["scene"]
    scene_id = scene["scene_id"]
    checkpoint_id = f"video_{scene_id}"

    if checkpoint_exists(checkpoint_id):
        return {"video_outputs": {f"scene_{scene_id}": load_checkpoint(checkpoint_id)}}

    primary_char = scene["characters"][0] if scene.get("characters") else ""
    char_image = resolve_character_image(primary_char) if primary_char else None

    visual_cues = " ".join(d.get("visual_cue", "") for d in scene.get("dialogue", []))
    raw_video = query_stock_footage(
        location=scene["location"],
        visual_cue=visual_cues,
        action=scene["action"],
        character_image=char_image,
    )
    commit_memory(raw_video, checkpoint_id=checkpoint_id)
    return {"video_outputs": {f"scene_{scene_id}": raw_video}}
