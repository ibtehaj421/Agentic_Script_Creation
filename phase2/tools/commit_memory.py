"""Checkpoint persistence.

Writes each checkpoint to `memory/checkpoints/<id>.json` so subsequent
runs can resume instead of redoing expensive work (edge-tts calls,
ffmpeg renders, etc.).
"""
from __future__ import annotations

import json
import os

from config import CHECKPOINT_DIR


def _path(checkpoint_id: str) -> str:
    return os.path.join(CHECKPOINT_DIR, f"{checkpoint_id}.json")


def commit_memory(data, checkpoint_id: str) -> str:
    path = _path(checkpoint_id)
    with open(path, "w") as f:
        json.dump({"checkpoint_id": checkpoint_id, "data": data}, f)
    return path


def checkpoint_exists(checkpoint_id: str) -> bool:
    return os.path.exists(_path(checkpoint_id))


def load_checkpoint(checkpoint_id: str):
    with open(_path(checkpoint_id)) as f:
        return json.load(f)["data"]
