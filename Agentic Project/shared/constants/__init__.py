"""Shared constants used across phases.

Single source of truth — voice pool, emotion prosody, target resolution,
default durations, etc. Agents import from here so tuning one knob
propagates everywhere.
"""
from __future__ import annotations

# ── Video ──────────────────────────────────────────────────────────────
# Pollinations free tier hard-caps the long edge at 1024 px, so we render
# at the source's native resolution (1024×576) instead of upscaling to
# 1080p. Smaller container, but every pixel is real — no resampling
# softness.
TARGET_WIDTH = 1024
TARGET_HEIGHT = 576
TARGET_FPS = 25
BACKGROUND_REQ_WIDTH = 1024     # = TARGET_WIDTH (Pollinations native cap)
BACKGROUND_REQ_HEIGHT = 576     # = TARGET_HEIGHT
PORTRAIT_SIZE = 1024            # square portrait via Pollinations

DEFAULT_SCENE_DURATION_S = 6.0
MIN_SCENE_DURATION_S = 3.0
TRANSITION_DURATION_S = 0.5

# Encoder profile. videotoolbox is hardware-accelerated on Apple Silicon
# and ~6-8x faster than libx264 at comparable quality, BUT it silently
# outputs yuvj420p (full-range, JPEG-style) and Firefox refuses to play
# those files in HTML5 <video>. Default to libx264 which produces clean
# yuv420p tv-range that every browser handles. Override via env var if
# you really want videotoolbox speed and don't care about Firefox demo
# playback.
import os as _os
VIDEO_ENCODER = _os.getenv("VIDEO_ENCODER", "libx264")
VIDEO_ENCODER_FALLBACK = "libx264"
VIDEO_BITRATE = "5M"

# ── Audio ──────────────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 24000
AUDIO_CHANNELS = 1
DEFAULT_BGM_VOLUME = 0.30  # 30% — was 0.12, inaudible on laptop speakers

# ── TTS voices: deterministic hash → voice mapping ─────────────────────
# Two providers, hot-swap at runtime based on whether ELEVENLABS_API_KEY
# is set (config.py): ElevenLabs is significantly more natural; edge-tts
# is the keyless fallback when EL is unavailable / quota-exhausted.

# Edge-tts pool, split by gender so the voice picker can pick a
# gender-appropriate voice for the character. All entries verified live
# on 2026-04-25.
VOICE_POOL_MALE = [
    "en-US-AndrewMultilingualNeural",   # warm, confident male
    "en-US-BrianMultilingualNeural",    # neutral male
    "en-AU-WilliamMultilingualNeural",  # AU male, mature
    "en-US-RogerNeural",                # older male
    "en-US-ChristopherNeural",          # mature male
    "en-GB-RyanNeural",                 # UK male
]
VOICE_POOL_FEMALE = [
    "en-US-AvaMultilingualNeural",      # expressive, friendly female
    "en-US-EmmaMultilingualNeural",     # warm female
    "en-US-AriaNeural",                 # versatile female
    "en-GB-SoniaNeural",                # UK female
]
# Backwards-compat: keep VOICE_POOL as the union for any code that
# imports it without a gender hint.
VOICE_POOL = VOICE_POOL_MALE + VOICE_POOL_FEMALE

# ElevenLabs voices — modern v3 library entries. We deliberately exclude
# every voice tagged `use_case=social_media` (Adam, Brian, Liam) — those
# sound like the "streamer TTS" voice every twitch chat has heard a
# thousand times. Conversational and narrative_story voices sound
# dramatically more like real people. Verified against /v1/voices on
# 2026-04-26.
ELEVENLABS_VOICE_POOL_MALE = [
    "CwhRBWXzGAHq8TQ4Fs17",  # Roger    — laid-back, casual, resonant (US, conv)
    "cjVigY5qzO86Huf0OWal",  # Eric     — smooth, trustworthy (US, conv)
    "iP95p4xoKVk53GoZ742B",  # Chris    — charming, down-to-earth (US, conv)
    "bIHbv24MWmeRgasZH58o",  # Will     — relaxed optimist (US, conv)
    "IKne3meq5aSn9XLyUdCD",  # Charlie  — deep, confident, energetic (AU, conv)
    "JBFqnCBsd6RMkjVDRZzb",  # George   — warm storyteller (UK, narrative)
]
ELEVENLABS_VOICE_POOL_FEMALE = [
    "EXAVITQu4vr4xnSDxMaL",  # Sarah    — mature, reassuring, confident (US)
    "cgSgspJ2msm6clMCkdW9",  # Jessica  — playful, bright, warm (US, conv)
    "hpp4J3VqNfWAUOO0d1Us",  # Bella    — professional, bright, warm (US)
    "pFZP5JQG7iQjIQuC4Bku",  # Lily     — velvety actress (UK)
]
ELEVENLABS_VOICE_POOL = ELEVENLABS_VOICE_POOL_MALE + ELEVENLABS_VOICE_POOL_FEMALE

# Style overrides per gender. Keys are voice_style values the character
# designer picks; values are voice_ids in the matching gender pool. The
# voice picker first resolves the character's gender, then looks up the
# style in the matching dict — no cross-gender mismatches possible.
ELEVENLABS_STYLE_OVERRIDES_MALE = {
    "deep":       "CwhRBWXzGAHq8TQ4Fs17",  # Roger
    "warm":       "JBFqnCBsd6RMkjVDRZzb",  # George
    "crisp":      "onwK4e9ZLuTAKqWW03F9",  # Daniel (steady broadcaster, UK)
    "raspy":      "pqHfZKP75CvOlQylNhV4",  # Bill
    "whispered":  "iP95p4xoKVk53GoZ742B",  # Chris
    "commanding": "cjVigY5qzO86Huf0OWal",  # Eric
    "youthful":   "bIHbv24MWmeRgasZH58o",  # Will
    "elderly":    "pqHfZKP75CvOlQylNhV4",  # Bill
    "sultry":     "cjVigY5qzO86Huf0OWal",  # Eric (smooth) — male equivalent
    "monotone":   "onwK4e9ZLuTAKqWW03F9",  # Daniel
    "british":    "JBFqnCBsd6RMkjVDRZzb",  # George
}
ELEVENLABS_STYLE_OVERRIDES_FEMALE = {
    "deep":       "EXAVITQu4vr4xnSDxMaL",  # Sarah (mature, lower register)
    "warm":       "hpp4J3VqNfWAUOO0d1Us",  # Bella
    "crisp":      "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "raspy":      "pFZP5JQG7iQjIQuC4Bku",  # Lily (textured)
    "whispered":  "hpp4J3VqNfWAUOO0d1Us",  # Bella
    "commanding": "EXAVITQu4vr4xnSDxMaL",  # Sarah (confident)
    "youthful":   "cgSgspJ2msm6clMCkdW9",  # Jessica
    "elderly":    "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "sultry":     "pFZP5JQG7iQjIQuC4Bku",  # Lily
    "monotone":   "hpp4J3VqNfWAUOO0d1Us",  # Bella
    "british":    "pFZP5JQG7iQjIQuC4Bku",  # Lily
}
# Legacy union kept for any importer that doesn't pass a gender.
ELEVENLABS_STYLE_OVERRIDES = ELEVENLABS_STYLE_OVERRIDES_MALE

# Emotion → SSML-friendly (rate, pitch) modulation
EMOTION_PROSODY = {
    "happy":      ("+10%", "+5Hz"),
    "sad":        ("-15%", "-3Hz"),
    "angry":      ("+15%", "+8Hz"),
    "fearful":    ("+5%",  "+10Hz"),
    "surprised":  ("+20%", "+10Hz"),
    "urgent":     ("+15%", "+4Hz"),
    "tense":      ("+5%",  "+2Hz"),
    "determined": ("+0%",  "+3Hz"),
    "reflective": ("-10%", "-2Hz"),
    "whispered":  ("-20%", "-4Hz"),
    "neutral":    ("+0%",  "+0Hz"),
}

# Scene mood → real BGM track preference (file basename, looked up under
# `data/bgm/library/{mood}/<file>.mp3`). When the file is missing the
# synth fallback in audio_tools/bgm_tool.py kicks in. Tracks are sourced
# from Serge Quadrado's CC-BY 3.0 "Ambient Film Music" collection on
# archive.org — see scripts/fetch_bgm.py for download.
MOOD_TO_BGM_FILE = {
    "tense":       "Night.mp3",
    "urgent":      "Moment.mp3",
    "suspense":    "Twilight.mp3",
    "mysterious":  "Twilight.mp3",
    "action":      "Fantasy.mp3",
    "happy":       "Harmony.mp3",
    "sad":         "Funeral.mp3",
    "reflective":  "Meditation.mp3",
    "determined":  "Moment.mp3",
    "neutral":     "Harmony.mp3",
}

# Synth-fallback parameters (used when no library file matches the mood)
MOOD_TO_BGM = {
    "tense":       {"root": 110, "vol": 0.30},
    "urgent":      {"root": 130, "vol": 0.30},
    "suspense":    {"root": 98,  "vol": 0.30},
    "happy":       {"root": 220, "vol": 0.28},
    "sad":         {"root": 87,  "vol": 0.32},
    "mysterious":  {"root": 98,  "vol": 0.30},
    "action":      {"root": 164, "vol": 0.30},
    "reflective":  {"root": 130, "vol": 0.26},
    "determined":  {"root": 146, "vol": 0.28},
    "neutral":     {"root": 130, "vol": 0.26},
}


# ── Edit intent taxonomy ───────────────────────────────────────────────
# Canonical intents the classifier should emit. Kept in sync with tests.
KNOWN_INTENTS: tuple[str, ...] = (
    "change_voice_tone",
    "change_voice_character",
    "add_background_music",
    "remove_background_music",
    "regenerate_scene_audio",
    # Generic catch-all for any free-text "make scene N look ..." directive
    # (darker, more orange, warmer, add buildings, etc). Carries structured
    # `brightness_delta`, `saturation_delta`, `hue_shift`, `prompt_suffix`.
    "modify_scene_visual",
    # Kept as legacy aliases — handled identically to modify_scene_visual
    # with preset deltas, so existing test queries still classify cleanly.
    "make_scene_darker",
    "make_scene_brighter",
    "change_character_design",
    "regenerate_scene_image",
    "remove_subtitle",
    "add_subtitle",
    "speed_up_scene",
    "slow_down_scene",
    "change_transition",
    "regenerate_script",
    "change_scene_location",
)
