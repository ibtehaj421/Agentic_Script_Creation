"""Phase 2 configuration. Everything is free / local by default."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

# Where Phase 1 dropped its artefacts. Either the sibling copy inside
# phase2/phase1/ (used by the submitted Phase 2 scaffolding) or the
# canonical project/outputs directory works.
PHASE1_DIR = ROOT / "phase1"
PHASE1_IMAGE_DIR_CANDIDATES = [
    PHASE1_DIR / "outputs" / "characters",
    ROOT.parent / "outputs" / "images",
]

CHECKPOINT_DIR = ROOT / "memory" / "checkpoints"
AUDIO_OUT_DIR = ROOT / "outputs" / "audio"
VIDEO_OUT_DIR = ROOT / "outputs" / "video"
RAW_SCENES_DIR = ROOT / "outputs" / "raw_scenes"
LOGS_DIR = ROOT / "outputs" / "logs"

for directory in (CHECKPOINT_DIR, AUDIO_OUT_DIR, VIDEO_OUT_DIR, RAW_SCENES_DIR, LOGS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def resolve_character_image(character_name: str) -> str | None:
    """Try to locate the character reference image Phase 1 produced.

    Accepts a handful of case/spacing variants so this works with either
    phase1/outputs/characters/ (title-cased) or project/outputs/images/.
    """
    variants = {
        character_name.replace(" ", "_"),
        character_name.title().replace(" ", "_"),
        character_name.lower().replace(" ", "_"),
        character_name.upper().replace(" ", "_"),
    }
    for base in PHASE1_IMAGE_DIR_CANDIDATES:
        if not base.exists():
            continue
        for v in variants:
            p = base / f"{v}.png"
            if p.exists():
                return str(p)
    return None
