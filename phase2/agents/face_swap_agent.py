"""Face Swap Agent.

Role:   Maps a validated character identity onto the generated frames.
Tools:  face_swapper, identity_validator (MCP-exposed).
"""
from __future__ import annotations

from config import resolve_character_image
from tools.commit_memory import checkpoint_exists, commit_memory, load_checkpoint
from tools.face_swapper import face_swapper
from tools.identity_validator import identity_validator


def face_swap_node(payload: dict) -> dict:
    scene = payload["scene"]
    video_outputs = payload.get("video_outputs", {})
    scene_id = scene["scene_id"]
    checkpoint_id = f"faceswap_{scene_id}"

    if checkpoint_exists(checkpoint_id):
        return {"face_swapped_outputs": {f"scene_{scene_id}": load_checkpoint(checkpoint_id)}}

    raw_video = video_outputs.get(f"scene_{scene_id}")
    if not raw_video:
        return {}

    primary_char = scene["characters"][0] if scene.get("characters") else ""
    char_image = resolve_character_image(primary_char) if primary_char else None
    if not char_image:
        return {"errors": [f"[face_swap] No Phase 1 image found for {primary_char!r} (scene {scene_id})"]}

    if not identity_validator(primary_char, char_image):
        return {"errors": [f"[face_swap] Identity validation failed for scene {scene_id} / {primary_char}"]}

    swapped = face_swapper(char_image, raw_video)
    commit_memory(swapped, checkpoint_id=checkpoint_id)
    return {"face_swapped_outputs": {f"scene_{scene_id}": swapped}}
