"""Project-wide configuration.

One module, imported by every phase. Creates output directories on import
and centralises paths + API keys.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
# Fallback: the root .env one level up (shared GROQ key in repo root)
load_dotenv(ROOT.parent / ".env", override=False)

# Make imports like `from config import ...` work when running scripts that
# are not direct children of ROOT (e.g. `python -m backend.app`).
import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))

# ── Directories ────────────────────────────────────────────────────────
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"
TEMP_DIR = DATA_DIR / "temp"
STATE_VERSIONS_DIR = DATA_DIR / "state_versions"
STATE_DB = DATA_DIR / "state.sqlite"

IMAGES_DIR = OUTPUTS_DIR / "images"
AUDIO_DIR = OUTPUTS_DIR / "audio"
VIDEO_DIR = OUTPUTS_DIR / "video"
SCENES_DIR = OUTPUTS_DIR / "scenes"
FINAL_DIR = OUTPUTS_DIR / "final"
LOG_DIR = OUTPUTS_DIR / "logs"

for d in (
    DATA_DIR, OUTPUTS_DIR, TEMP_DIR, STATE_VERSIONS_DIR,
    IMAGES_DIR, AUDIO_DIR, VIDEO_DIR, SCENES_DIR, FINAL_DIR, LOG_DIR,
):
    d.mkdir(parents=True, exist_ok=True)

# ── Credentials / model config ─────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ElevenLabs is used as the primary TTS provider when a key is present;
# we fall back to free edge-tts otherwise (or if quota is exhausted).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# fal.ai is used as the primary image source when a key is present (FLUX
# at native HD); falls back to Pollinations (capped at 1024×576) otherwise.
FAL_KEY = os.getenv("FAL_KEY", "")
FAL_IMAGE_MODEL = os.getenv("FAL_IMAGE_MODEL", "fal-ai/flux/schnell")
