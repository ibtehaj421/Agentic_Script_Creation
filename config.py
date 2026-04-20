"""Project-wide configuration and directory wiring.

Imported by both the Phase 1 agents and the MCP server so they agree on
where artefacts live on disk.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
IMAGE_DIR = OUTPUT_DIR / "images"
MEMORY_DIR = ROOT / "memory" / "chroma"

for d in (OUTPUT_DIR, IMAGE_DIR, MEMORY_DIR):
    d.mkdir(parents=True, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
