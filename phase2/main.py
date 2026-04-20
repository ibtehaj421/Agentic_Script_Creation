"""Entry point for Phase 2 — THE STUDIO FLOOR.

On every run this script:
    1. Pulls the latest scene_manifest.json and character images from the
       canonical Phase 1 output directory (project/outputs/).
    2. Detects whether the manifest changed since the last run (hash-based).
       If so, wipes stale checkpoints and media so the pipeline regenerates
       against the new content.
    3. Invokes the LangGraph pipeline.

Flags:
    --fresh   Force a full rebuild even if the manifest hash is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402 — triggers directory creation + env loading
from config import (  # noqa: E402
    AUDIO_OUT_DIR,
    CHECKPOINT_DIR,
    LOGS_DIR,
    RAW_SCENES_DIR,
    VIDEO_OUT_DIR,
)
from graph.studio_graph import app  # noqa: E402
from state.studio_state import StudioState  # noqa: E402

PHASE1_OUTPUT_DIR = ROOT.parent / "outputs"
PHASE1_MANIFEST = PHASE1_OUTPUT_DIR / "scene_manifest.json"
PHASE1_IMAGES_DIR = PHASE1_OUTPUT_DIR / "images"

LOCAL_MANIFEST = ROOT / "scene_manifest.json"
LOCAL_CHARACTERS_DIR = ROOT / "phase1" / "outputs" / "characters"
MANIFEST_HASH_FILE = CHECKPOINT_DIR / "_manifest.hash"


def _hash_file(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _wipe(dir_path: Path) -> None:
    if not dir_path.exists():
        return
    for item in dir_path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def sync_from_phase1(force: bool) -> Path:
    """Bring the canonical Phase 1 artefacts into phase2/ and return the
    manifest path to load. Wipes stale caches when inputs changed.
    """
    # Copy manifest (prefer canonical project/outputs/ copy if present)
    if PHASE1_MANIFEST.exists():
        LOCAL_MANIFEST.write_bytes(PHASE1_MANIFEST.read_bytes())
        source = f"project/outputs/ ({PHASE1_MANIFEST.name})"
    elif LOCAL_MANIFEST.exists():
        source = f"phase2/{LOCAL_MANIFEST.name} (fallback)"
    else:
        raise FileNotFoundError(
            "No scene_manifest.json found in project/outputs/ or phase2/. "
            "Run Phase 1 first."
        )
    print(f"📜 Manifest source: {source}")

    # Copy character images
    if PHASE1_IMAGES_DIR.exists():
        LOCAL_CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        # Start from scratch each time so deleted phase1 characters don't
        # linger and confuse the identity resolver.
        _wipe(LOCAL_CHARACTERS_DIR)
        for img in PHASE1_IMAGES_DIR.glob("*.png"):
            shutil.copy2(img, LOCAL_CHARACTERS_DIR / img.name)
        print(f"🖼  Synced {len(list(LOCAL_CHARACTERS_DIR.glob('*.png')))} character images")

    # Detect manifest change -> invalidate caches
    current_hash = _hash_file(LOCAL_MANIFEST)
    prior_hash = (
        MANIFEST_HASH_FILE.read_text().strip()
        if MANIFEST_HASH_FILE.exists()
        else None
    )

    if force or prior_hash != current_hash:
        reason = "--fresh flag" if force else "manifest changed"
        print(f"♻  Wiping stale caches ({reason})")
        for d in (CHECKPOINT_DIR, AUDIO_OUT_DIR, VIDEO_OUT_DIR, RAW_SCENES_DIR, LOGS_DIR):
            _wipe(d)
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST_HASH_FILE.write_text(current_hash)
    else:
        print("♻  Reusing cached checkpoints (manifest unchanged)")

    return LOCAL_MANIFEST


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Wipe all checkpoints and outputs before running",
    )
    args = parser.parse_args()

    manifest_path = sync_from_phase1(force=args.fresh)
    with open(manifest_path) as f:
        manifest = json.load(f)

    initial_state: StudioState = {
        "scene_manifest": manifest,
        "task_graph": [],
        "audio_outputs": {},
        "video_outputs": {},
        "face_swapped_outputs": {},
        "final_outputs": {},
        "errors": [],
    }

    print("🎬 Initializing The Studio Floor Pipeline...")
    result = app.invoke(initial_state)

    print("\n=== Final Outputs ===")
    for scene_id, path in result.get("final_outputs", {}).items():
        print(f"  {scene_id}: {path}")

    if result.get("errors"):
        print("\n=== Errors ===")
        for err in result["errors"]:
            print(f"  {err}")


if __name__ == "__main__":
    main()
