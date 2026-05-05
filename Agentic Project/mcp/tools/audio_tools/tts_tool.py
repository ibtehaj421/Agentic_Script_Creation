"""Text-to-speech.

Two providers, hot-swapped at runtime:
  * ElevenLabs — primary when ELEVENLABS_API_KEY is set. Significantly
    more natural prosody (especially with eleven_multilingual_v2);
    emotion drives `voice_settings` (stability/style).
  * edge-tts — keyless fallback. Used when the EL key is missing,
    quota is exhausted, or the API call errors. Emotion drives SSML
    rate/pitch.

Character name is hashed into a deterministic voice from the active
provider's pool, so the same character keeps the same voice across
scenes. The cache key includes the provider so outputs from the two
backends don't collide on disk.
"""
from __future__ import annotations

import asyncio
import hashlib
import subprocess
from pathlib import Path

import edge_tts
import httpx

from config import AUDIO_DIR, ELEVENLABS_API_KEY, ELEVENLABS_MODEL
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    ELEVENLABS_STYLE_OVERRIDES,
    ELEVENLABS_STYLE_OVERRIDES_FEMALE,
    ELEVENLABS_STYLE_OVERRIDES_MALE,
    ELEVENLABS_VOICE_POOL,
    ELEVENLABS_VOICE_POOL_FEMALE,
    ELEVENLABS_VOICE_POOL_MALE,
    EMOTION_PROSODY,
    VOICE_POOL,
    VOICE_POOL_FEMALE,
    VOICE_POOL_MALE,
)
from shared.utils import hash_short, job_dir, safe_filename


# ── edge-tts voice-style mapping (used only when falling back) ─────────
EDGE_STYLE_OVERRIDES_MALE = {
    "deep":       "en-US-AndrewMultilingualNeural",
    "warm":       "en-US-AndrewMultilingualNeural",
    "crisp":      "en-US-BrianMultilingualNeural",
    "raspy":      "en-US-ChristopherNeural",
    "whispered":  "en-US-BrianMultilingualNeural",
    "commanding": "en-US-AndrewMultilingualNeural",
    "youthful":   "en-US-BrianMultilingualNeural",
    "elderly":    "en-US-RogerNeural",
    "sultry":     "en-US-RogerNeural",
    "monotone":   "en-US-BrianMultilingualNeural",
    "british":    "en-GB-RyanNeural",
}
EDGE_STYLE_OVERRIDES_FEMALE = {
    "deep":       "en-US-AriaNeural",
    "warm":       "en-US-EmmaMultilingualNeural",
    "crisp":      "en-US-AvaMultilingualNeural",
    "raspy":      "en-US-AriaNeural",
    "whispered":  "en-US-AvaMultilingualNeural",
    "commanding": "en-US-AriaNeural",
    "youthful":   "en-US-EmmaMultilingualNeural",
    "elderly":    "en-GB-SoniaNeural",
    "sultry":     "en-US-AriaNeural",
    "monotone":   "en-US-AvaMultilingualNeural",
    "british":    "en-GB-SoniaNeural",
}


# Trailing silence added to every TTS line. Real conversation has
# 400-1000 ms between turns; without it back-to-back synthesized lines
# sound robotic. Including the pad in the per-line wav means the timing
# manifest (built from probed durations) stays aligned with subtitles.
_INTER_LINE_PAUSE_S = 0.55


# ── ElevenLabs voice_settings per emotion ─────────────────────────────
# stability        (0-1) lower = more emotional variation
# similarity_boost (0-1) how strictly to track voice timbre
# style            (0-1) exaggerate stylistic traits (multilingual_v2 only)
EL_EMOTION_SETTINGS: dict[str, dict[str, float]] = {
    "neutral":    dict(stability=0.50, similarity_boost=0.75, style=0.05),
    "happy":      dict(stability=0.40, similarity_boost=0.75, style=0.35),
    "sad":        dict(stability=0.60, similarity_boost=0.80, style=0.20),
    "angry":      dict(stability=0.30, similarity_boost=0.75, style=0.45),
    "fearful":    dict(stability=0.30, similarity_boost=0.75, style=0.40),
    "fear":       dict(stability=0.30, similarity_boost=0.75, style=0.45),
    "surprised":  dict(stability=0.35, similarity_boost=0.75, style=0.40),
    "urgent":     dict(stability=0.35, similarity_boost=0.75, style=0.35),
    "tense":      dict(stability=0.40, similarity_boost=0.80, style=0.30),
    "determined": dict(stability=0.45, similarity_boost=0.78, style=0.25),
    "reflective": dict(stability=0.55, similarity_boost=0.80, style=0.15),
    # Whispered: lower stability + higher style so the v2 model takes the
    # `[whispers]` audio tag (prepended to text) more aggressively.
    "whispered":  dict(stability=0.30, similarity_boost=0.85, style=0.40),
    "whisper":    dict(stability=0.30, similarity_boost=0.85, style=0.40),
    "panic":      dict(stability=0.25, similarity_boost=0.75, style=0.50),
    "desperate":  dict(stability=0.30, similarity_boost=0.75, style=0.45),
    "anxious":    dict(stability=0.35, similarity_boost=0.78, style=0.35),
    "curious":    dict(stability=0.45, similarity_boost=0.75, style=0.20),
    "caution":    dict(stability=0.50, similarity_boost=0.78, style=0.15),
    "cautious":   dict(stability=0.50, similarity_boost=0.78, style=0.15),
    "intense":    dict(stability=0.35, similarity_boost=0.78, style=0.35),
    "alert":      dict(stability=0.40, similarity_boost=0.75, style=0.30),
    "reassuring": dict(stability=0.55, similarity_boost=0.80, style=0.20),
    "frustrated": dict(stability=0.35, similarity_boost=0.75, style=0.40),
    "suspicious": dict(stability=0.45, similarity_boost=0.78, style=0.25),
}


# ElevenLabs Multilingual v2 advertises support for inline audio tags
# like [whispers], [laughs], [sighs] — but in practice the v2 model often
# READS the tag aloud as literal text instead of interpreting it. We
# leave this map empty so no tags are injected. Whisper is handled
# acoustically in `_mp3_to_wav_with_pad` via volume cut + highpass +
# treble lift, which produces a reliable whisper without depending on
# the model honoring a tag.
_EL_EMOTION_TAG: dict[str, str] = {}


def _hash_pick(speaker: str, pool: list[str]) -> str:
    h = int(hashlib.md5(speaker.encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


def _voice_for_el(speaker: str, voice_style: str | None, gender: str = "neutral") -> str:
    """Resolve a speaker → ElevenLabs voice_id, gender-filtered.

    Falls back to the union pool/overrides when gender is "neutral" or
    unrecognised, preserving prior behaviour for callers that don't
    populate the gender field.
    """
    g = (gender or "neutral").lower()
    if g == "male":
        pool = ELEVENLABS_VOICE_POOL_MALE
        overrides = ELEVENLABS_STYLE_OVERRIDES_MALE
    elif g == "female":
        pool = ELEVENLABS_VOICE_POOL_FEMALE
        overrides = ELEVENLABS_STYLE_OVERRIDES_FEMALE
    else:
        pool = ELEVENLABS_VOICE_POOL
        overrides = ELEVENLABS_STYLE_OVERRIDES
    if voice_style and voice_style.lower() in overrides:
        return overrides[voice_style.lower()]
    return _hash_pick(speaker, pool)


def _voice_for_edge(speaker: str, voice_style: str | None, gender: str = "neutral") -> str:
    g = (gender or "neutral").lower()
    if g == "male":
        pool = VOICE_POOL_MALE
        overrides = EDGE_STYLE_OVERRIDES_MALE
    elif g == "female":
        pool = VOICE_POOL_FEMALE
        overrides = EDGE_STYLE_OVERRIDES_FEMALE
    else:
        pool = VOICE_POOL
        overrides = EDGE_STYLE_OVERRIDES_MALE  # legacy union (mostly male)
    if voice_style and voice_style.lower() in overrides:
        return overrides[voice_style.lower()]
    return _hash_pick(speaker, pool)


def _rewrite_text_for_emotion(text: str, emotion: str) -> str:
    """Adjust the *text sent to TTS* (not the subtitle) so models that
    interpret punctuation/casing render the requested emotion. The
    AudioSegment record + subtitle continue to carry the original line
    text, so on-screen captions stay clean.
    """
    em = (emotion or "").lower()
    s = text.strip()
    if not s:
        return text
    if em in ("shout", "shouting"):
        # Trailing "!!" + strip terminal period. Don't ALL-CAPS — TTS reads
        # caps-only words letter-by-letter for some voices.
        return s.rstrip(".?!") + "!!"
    if em in ("angry", "anger", "frustrated"):
        return s if s.endswith("!") else s.rstrip(".") + "!"
    if em in ("sad", "sorrow", "grief", "reflective"):
        # Trailing ellipsis cues a slow, falling delivery for most TTS.
        if s.endswith("..."): return s
        return s.rstrip(".?!") + "..."
    if em in ("happy", "joy", "excited", "surprised", "happy"):
        return s if s.endswith("!") else s.rstrip(".") + "!"
    if em in ("panic", "panicked", "fearful", "fear", "desperate", "urgent"):
        return s if s.endswith("!") else s.rstrip(".") + "!"
    return text


def _post_filter_for_emotion(emotion: str) -> str:
    """ffmpeg filter chain (without leading comma) appended after `apad`
    to acoustically nudge the output toward the requested emotion.
    Returns empty string for emotions where voice_settings + text cues
    are enough on their own."""
    em = (emotion or "").lower()
    if em in ("whisper", "whispered"):
        # -8 dB + thin chest resonance + breath emphasis = real whisper
        return "volume=0.45,highpass=f=100,treble=g=4"
    if em in ("shout", "shouting"):
        # Boost + light compression + treble lift gives the harsher,
        # forward-projected feel of shouting without clipping.
        return "volume=1.35,acompressor=threshold=-18dB:ratio=3:attack=10:release=200,treble=g=2"
    if em in ("angry", "anger", "frustrated"):
        return "acompressor=threshold=-20dB:ratio=2.5:attack=15:release=180,treble=g=2"
    if em in ("sad", "sorrow", "grief"):
        # Slower, muffled (chest-voice forward), slightly quieter
        return "atempo=0.93,lowpass=f=4500,volume=0.88"
    if em in ("happy", "joy", "excited", "surprised"):
        return "atempo=1.05,treble=g=2"
    if em in ("panic", "panicked", "fearful", "fear", "desperate"):
        return "atempo=1.08,treble=g=3,acompressor=threshold=-22dB:ratio=2"
    if em in ("monotone", "robotic"):
        # ElevenLabs voice_settings stability=0.95 already produces this
        # — no DSP needed.
        return ""
    if em in ("reflective",):
        return "atempo=0.95,lowpass=f=5000"
    return ""


def _mp3_to_wav_with_pad(mp3_path: Path, out: Path, emotion: str = "") -> None:
    """Convert TTS mp3 to padded wav, optionally applying emotion-specific
    DSP (whisper, shout, angry, sad, panic, …) so the audible result
    matches the requested emotion regardless of what the AI model did."""
    extra_chain = _post_filter_for_emotion(emotion)
    extra = f",{extra_chain}" if extra_chain else ""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(mp3_path),
            "-af", f"apad=pad_dur={_INTER_LINE_PAUSE_S:.3f}{extra}",
            "-ar", str(AUDIO_SAMPLE_RATE),
            "-ac", str(AUDIO_CHANNELS),
            str(out),
        ],
        check=True,
    )


def _synth_elevenlabs(text: str, voice_id: str, emotion: str, out: Path) -> None:
    settings = EL_EMOTION_SETTINGS.get(emotion.lower(), EL_EMOTION_SETTINGS["neutral"])
    # Optional inline audio tag (currently empty — v2 reads them as text).
    tag = _EL_EMOTION_TAG.get(emotion.lower(), "")
    # Adjust punctuation/casing per emotion (! for shout/anger, ... for sad,
    # etc.) so ElevenLabs' prosody picks up on it. The subtitle/AudioSegment
    # still uses the original line, so on-screen captions stay clean.
    cued_text = _rewrite_text_for_emotion(text, emotion)
    body = {
        "text": f"{tag}{cued_text}" if tag else cued_text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {**settings, "use_speaker_boost": True},
    }
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "accept": "audio/mpeg"},
        json=body,
        timeout=60,
    )
    if r.status_code == 401:
        raise RuntimeError("elevenlabs: 401 (key invalid or revoked)")
    if r.status_code == 402:
        raise RuntimeError("elevenlabs: 402 (quota exhausted)")
    if r.status_code != 200 or not r.content:
        raise RuntimeError(f"elevenlabs: {r.status_code} {r.text[:120]}")

    mp3 = out.with_suffix(".mp3")
    mp3.write_bytes(r.content)
    _mp3_to_wav_with_pad(mp3, out, emotion=emotion)
    mp3.unlink(missing_ok=True)


async def _synth_edge_async(text: str, voice: str, rate: str, pitch: str, out: Path,
                            emotion: str = "") -> None:
    mp3 = out.with_suffix(".mp3")
    cued_text = _rewrite_text_for_emotion(text, emotion)
    await edge_tts.Communicate(text=cued_text, voice=voice, rate=rate, pitch=pitch).save(str(mp3))
    _mp3_to_wav_with_pad(mp3, out, emotion=emotion)
    mp3.unlink(missing_ok=True)


def _cache_key(provider: str, speaker: str, line: str, emotion: str,
               voice_style: str | None, override_voice: str | None,
               gender: str = "neutral") -> str:
    # `gender` is part of the key so a gender flip (story regen) doesn't
    # serve a stale wav from before the fix.
    return hash_short(
        f"{provider}|{speaker}|{line}|{emotion}|{voice_style}|{override_voice}|{gender}|pad055v7emo",
        10,
    )


class TTSTool(BaseTool):
    spec = ToolSpec(
        name="tts_synthesize",
        description="Render one dialogue line. ElevenLabs primary, edge-tts fallback.",
        category="audio",
        schema={"speaker": "str", "line": "str", "emotion": "str", "voice_style": "str", "gender": "str"},
    )

    def run(
        self,
        speaker: str,
        line: str,
        emotion: str = "neutral",
        voice_style: str | None = None,
        override_voice: str | None = None,
        gender: str = "neutral",
        job_id: str | None = None,
    ) -> str:
        out_dir = job_dir(AUDIO_DIR, job_id)
        safe = safe_filename(speaker)

        # Try ElevenLabs first if a key is configured.
        if ELEVENLABS_API_KEY:
            key = _cache_key("el", speaker, line, emotion, voice_style, override_voice, gender)
            out = out_dir / f"{safe}_{key}.wav"
            if out.exists() and out.stat().st_size > 0:
                return str(out)

            voice_id = override_voice if (override_voice and len(override_voice) >= 16) \
                else _voice_for_el(speaker, voice_style, gender)
            try:
                print(f"  🎙  elevenlabs | {speaker} ({gender}) → {voice_id[:8]}… | emotion={emotion}")
                _synth_elevenlabs(line, voice_id, emotion, out)
                return str(out)
            except Exception as e:
                print(f"  ⚠  elevenlabs failed ({e}); falling back to edge-tts")
                # fall through to edge-tts path

        # edge-tts path (also used when EL key is absent)
        key = _cache_key("edge", speaker, line, emotion, voice_style, override_voice, gender)
        out = out_dir / f"{safe}_{key}.wav"
        if out.exists() and out.stat().st_size > 0:
            return str(out)

        voice = override_voice if (override_voice and override_voice.startswith("en-")) \
            else _voice_for_edge(speaker, voice_style, gender)
        rate, pitch = EMOTION_PROSODY.get(emotion.lower(), EMOTION_PROSODY["neutral"])
        print(f"  🎙  edge-tts | {speaker} ({gender}) → {voice} | emotion={emotion} (rate={rate}, pitch={pitch})")
        asyncio.run(_synth_edge_async(line, voice, rate, pitch, out, emotion=emotion))
        return str(out)
