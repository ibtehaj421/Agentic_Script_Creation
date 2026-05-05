"""Build SRT-ready timing segments from the audio manifest."""
from __future__ import annotations

from typing import List

from shared.schemas import PipelineState


def dialogue_segments_for(state: PipelineState, scene_id: int) -> List[dict]:
    """Return [{start_s, end_s, text}] for a single scene's dialogue."""
    segs = [s for s in state.audio.segments if s.scene_id == scene_id]
    return [
        {
            "start_s": seg.start_ms / 1000.0,
            "end_s": seg.end_ms / 1000.0,
            "text": f"{seg.speaker}: {seg.line}",
        }
        for seg in sorted(segs, key=lambda s: s.start_ms)
    ]
