"""Per-job phase-cache management.

Manual UI reruns and edit-agent rebuilds both need to wipe cached tool
outputs (TTS wavs, ken-burns/wav2lip MP4s, scene composites, generated
PNGs) before re-running a phase, otherwise the deterministic file-cache
returns the previous version and the rerun is silently a no-op. The
helpers here centralise that logic so every caller behaves identically.

Cascading order (each phase invalidates everything downstream):
    story  → wipes story + audio + video caches
    audio  → wipes audio + video caches
    video  → wipes video caches
"""
from __future__ import annotations

from pathlib import Path

from config import AUDIO_DIR, IMAGES_DIR, SCENES_DIR, VIDEO_DIR
from shared.schemas import PipelineState


def _wipe_dir(path: Path) -> None:
    """Recursively delete every file under `path`. Subdirectories are
    preserved (rglob walks them) so callers don't have to recreate
    structures like `_masks/` or `scene_backgrounds/`."""
    if not path.exists():
        return
    for child in path.rglob("*"):
        if child.is_file():
            try:
                child.unlink()
            except FileNotFoundError:
                pass


def clear_phase_cache(phase: str, state: PipelineState) -> None:
    """Wipe the caches a phase rerun would otherwise hit, plus the caches
    of every downstream phase whose inputs become stale. Also clears the
    state-level path pointers (character.image_path, scene_clips, etc.)
    so handlers don't try to reuse paths that no longer exist on disk."""
    job_id = state.job_id

    if phase in {"story"}:
        _wipe_dir(IMAGES_DIR / job_id)
        for c in state.story.characters:
            c.image_path = ""

    if phase in {"story", "audio"}:
        _wipe_dir(AUDIO_DIR / job_id)
        state.audio.segments = []
        state.audio.scene_audio = {}
        state.audio.bgm_tracks = {}

    if phase in {"story", "audio", "video"}:
        _wipe_dir(VIDEO_DIR / job_id)
        _wipe_dir(SCENES_DIR / job_id)
        state.video.scene_clips = {}
        state.video.final_mp4 = ""


__all__ = ["clear_phase_cache"]
