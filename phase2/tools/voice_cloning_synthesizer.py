# import os
# import time
# import hashlib
# import threading
# import requests
# from config import ELEVENLABS_API_KEY, AUDIO_OUT_DIR

# VOICE_POOL = [
#     "ouL9IsyrSnUkCmfnD02u", "6IwYbsNENZgAB1dtBZDp",
#     "mHX7OoPk2G45VMAuinIt", "RDSy0QN68yhrjuOgqzQ4", "zv0Q6YuQUa0P3IK62XgN"
# ]

# # One lock per voice ID — prevents concurrent requests to the same voice
# _voice_locks: dict[str, threading.Lock] = {vid: threading.Lock() for vid in VOICE_POOL}

# RETRY_STATUS_CODES = {409, 429}  # conflict + rate-limit
# MAX_RETRIES = 5
# BACKOFF_BASE = 1.5  # seconds; doubles each attempt


# def get_deterministic_voice(character_name: str) -> str:
#     hash_val = int(hashlib.md5(character_name.encode("utf-8")).hexdigest(), 16)
#     return VOICE_POOL[hash_val % len(VOICE_POOL)]


# def voice_cloning_synthesizer(speaker: str, line: str, emotion: str) -> str:
#     if not ELEVENLABS_API_KEY:
#         raise ValueError("ELEVENLABS_API_KEY is missing from .env file")

#     os.makedirs(AUDIO_OUT_DIR, exist_ok=True)

#     target_voice_id = get_deterministic_voice(speaker)
#     safe_speaker = speaker.replace(" ", "_")
#     output_path = os.path.join(AUDIO_OUT_DIR, f"{safe_speaker}_{abs(hash(line))}.wav")

#     url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice_id}"
#     headers = {
#         "Accept": "audio/mpeg",
#         "Content-Type": "application/json",
#         "xi-api-key": ELEVENLABS_API_KEY,
#     }
#     payload = {
#         "text": line,
#         "model_id": "eleven_multilingual_v2",
#         "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
#     }

#     print(f"🎙️ Requesting ElevenLabs audio for: {speaker} (voice {target_voice_id})...")

#     # Serialize requests that share the same voice ID
#     with _voice_locks[target_voice_id]:
#         for attempt in range(1, MAX_RETRIES + 1):
#             response = requests.post(url, json=payload, headers=headers)

#             if response.status_code == 200:
#                 with open(output_path, "wb") as f:
#                     f.write(response.content)
#                 print(f"✅ Successfully wrote: {output_path}")
#                 return output_path

#             if response.status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
#                 wait = BACKOFF_BASE * (2 ** (attempt - 1))
#                 print(
#                     f"⚠️  ElevenLabs {response.status_code} on attempt {attempt}/{MAX_RETRIES} "
#                     f"for '{speaker}'. Retrying in {wait:.1f}s…"
#                 )
#                 time.sleep(wait)
#                 continue

#             # Non-retryable error or retries exhausted
#             raise Exception(
#                 f"ElevenLabs API failed after {attempt} attempt(s): "
#                 f"{response.status_code} - {response.text}"
#             )
import sys
sys.path.insert(0, r"D:\MyLibs\python-packages")
import os
import hashlib
import soundfile as sf
from kokoro_onnx import Kokoro
from config import AUDIO_OUT_DIR

# Kokoro built-in voices
VOICE_POOL = [
    "af_bella",    # Female, American
    "af_sarah",    # Female, American
    "am_adam",     # Male, American
    "am_michael",  # Male, American
    "bf_emma",     # Female, British
]

# Emotion → speed mapping (Kokoro has no style tags, speed conveys emotion)
EMOTION_SPEED_MAP = {
    "happy":     1.15,
    "sad":       0.85,
    "angry":     1.2,
    "fearful":   1.1,
    "surprised": 1.25,
    "neutral":   1.0,
}

# Load model once globally — expensive to reload every call
MODEL_PATH = r"kokoro.onnx"
VOICES_PATH = r"voices-v1.0.bin"
_kokoro = Kokoro(MODEL_PATH, VOICES_PATH)


def get_deterministic_voice(character_name: str) -> str:
    hash_val = int(hashlib.md5(character_name.encode("utf-8")).hexdigest(), 16)
    return VOICE_POOL[hash_val % len(VOICE_POOL)]


def voice_cloning_synthesizer(speaker: str, line: str, emotion: str) -> str:
    os.makedirs(AUDIO_OUT_DIR, exist_ok=True)

    voice = get_deterministic_voice(speaker)
    speed = EMOTION_SPEED_MAP.get(emotion.lower(), 1.0)
    safe_speaker = speaker.replace(" ", "_")
    output_path = os.path.join(AUDIO_OUT_DIR, f"{safe_speaker}_{abs(hash(line))}.wav")

    print(f"🎙️ Synthesizing: {speaker} | voice: {voice} | emotion: {emotion} | speed: {speed}")

    samples, sample_rate = _kokoro.create(
        text=line,
        voice=voice,
        speed=speed,
        lang="en-us"
    )

    sf.write(output_path, samples, sample_rate)
    print(f"✅ Written: {output_path}")
    return output_path