"""Download BGM tracks for the library.

Source:  archive.org item `ambientforfilm` — Serge Quadrado's
         "Ambient Film Music" (CC-BY 3.0). Free for commercial use with
         attribution. We cite the collection in docs/REPORT.md.

Run once after `pip install -r requirements.txt`:

    python scripts/fetch_bgm.py

Tracks are saved under `data/bgm/library/<mood>/`. Re-running the script
is idempotent — already-downloaded files are skipped. To use your own
music, drop mp3s into `data/bgm/library/<mood>/` and the BGMTool will
prefer your files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DATA_DIR  # noqa: E402

LIBRARY_ROOT = DATA_DIR / "bgm" / "library"
BASE = "https://archive.org/download/ambientforfilm"

# mood -> (file_on_archive, attribution)
TRACKS = {
    "tense":       ("Night.mp3",                 "Night"),
    "urgent":      ("Moment.mp3",                "Moment"),
    "suspense":    ("Twilight.mp3",              "Twilight"),
    "mysterious":  ("Twilight.mp3",              "Twilight"),
    "action":      ("Fantasy.mp3",               "Fantasy"),
    "happy":       ("Harmony.mp3",               "Harmony"),
    "sad":         ("Funeral.mp3",               "Funeral"),
    "reflective":  ("Meditation.mp3",            "Meditation"),
    "determined":  ("Moment.mp3",                "Moment"),
    "neutral":     ("Harmony.mp3",               "Harmony"),
}

ATTRIBUTION = (
    'Music: "Ambient Film Music" by Serge Quadrado, used under CC BY 3.0.\n'
    "Source: https://archive.org/details/ambientforfilm\n"
)


def main() -> int:
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    (LIBRARY_ROOT / "ATTRIBUTION.txt").write_text(ATTRIBUTION)

    # de-dup: many moods reuse the same track
    seen: set[str] = set()
    print("┌── Fetching BGM into", LIBRARY_ROOT)

    for mood, (filename, _track_name) in TRACKS.items():
        mood_dir = LIBRARY_ROOT / mood
        mood_dir.mkdir(parents=True, exist_ok=True)
        out = mood_dir / filename
        if out.exists() and out.stat().st_size > 100_000:
            print(f"│  ✓ {mood:<12} {filename:<24} (cached)")
            continue
        url = f"{BASE}/{filename.replace(' ', '%20')}"
        print(f"│  ↓ {mood:<12} {filename:<24}", end="", flush=True)
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
                r.raise_for_status()
                with open(out, "wb") as f:
                    for chunk in r.iter_bytes(64 * 1024):
                        f.write(chunk)
            print(f"  ({out.stat().st_size // 1024} KB)")
            seen.add(filename)
        except Exception as e:
            print(f"  FAILED: {e}")

    print("└── Done.")
    print()
    print(ATTRIBUTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
