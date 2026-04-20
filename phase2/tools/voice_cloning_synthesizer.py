"""Voice Synthesis tool — edge-tts (free, keyless).

Maps each character name to a deterministic Microsoft Edge voice and
renders the line to a 24 kHz mono .wav file. Emotion is expressed via
SSML prosody (rate/pitch) — Edge voices don't expose style tokens, so
this is the best free proxy for "emotion-aware synthesis".
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from pathlib import Path

import edge_tts

from config import AUDIO_OUT_DIR

VOICE_POOL = [
    "en-US-GuyNeural",        # male, US
    "en-US-AriaNeural",       # female, US
    "en-US-JennyNeural",      # female, US, warm
    "en-US-ChristopherNeural",# male, US, deep
    "en-GB-RyanNeural",       # male, UK
    "en-GB-SoniaNeural",      # female, UK
    "en-AU-WilliamNeural",    # male, AU
    "en-AU-NatashaNeural",    # female, AU
]

# Emotion -> (rate, pitch) modulation. Edge doesn't take arbitrary emotion
# tags, so we map mood to prosody. Values are SSML-friendly strings.
EMOTION_PROSODY = {
    "happy":     ("+10%", "+5Hz"),
    "sad":       ("-15%", "-3Hz"),
    "angry":     ("+15%", "+8Hz"),
    "fearful":   ("+5%", "+10Hz"),
    "surprised": ("+20%", "+10Hz"),
    "urgent":    ("+15%", "+4Hz"),
    "tense":     ("+5%", "+2Hz"),
    "determined":("+0%", "+3Hz"),
    "reflective":("-10%", "-2Hz"),
    "neutral":   ("+0%", "+0Hz"),
}


def _voice_for(character_name: str) -> str:
    h = int(hashlib.md5(character_name.encode("utf-8")).hexdigest(), 16)
    return VOICE_POOL[h % len(VOICE_POOL)]


async def _synth(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None:
    communicator = edge_tts.Communicate(
        text=text, voice=voice, rate=rate, pitch=pitch
    )
    mp3_path = out_path.with_suffix(".mp3")
    await communicator.save(str(mp3_path))
    # edge-tts produces mp3; convert to 24kHz mono wav for downstream tools
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(mp3_path),
            "-ar", "24000", "-ac", "1",
            str(out_path),
        ],
        check=True,
    )
    mp3_path.unlink(missing_ok=True)


def voice_cloning_synthesizer(speaker: str, line: str, emotion: str) -> str:
    """Synthesize `line` as spoken by `speaker` with the given emotion.

    Returns the path to the generated .wav file.
    """
    os.makedirs(AUDIO_OUT_DIR, exist_ok=True)

    voice = _voice_for(speaker)
    rate, pitch = EMOTION_PROSODY.get(emotion.lower(), EMOTION_PROSODY["neutral"])
    safe_speaker = speaker.replace(" ", "_")
    stable_hash = hashlib.md5(f"{speaker}|{line}".encode("utf-8")).hexdigest()[:10]
    out_path = AUDIO_OUT_DIR / f"{safe_speaker}_{stable_hash}.wav"

    if out_path.exists() and out_path.stat().st_size > 0:
        return str(out_path)

    print(f"🎙️  edge-tts | {speaker} -> {voice} | emotion={emotion} (rate={rate}, pitch={pitch})")
    asyncio.run(_synth(line, voice, rate, pitch, out_path))
    return str(out_path)
