import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
# Model Paths
WAV2LIP_CHECKPOINT_PATH = os.getenv("WAV2LIP_CHECKPOINT_PATH", "Wav2Lip/checkpoints/wav2lip_gan.pth")
ROOP_DIR = os.getenv("ROOP_DIR", "roop")
COQUI_MODEL_NAME = os.getenv("COQUI_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2")

# Global Output Directories
CHECKPOINT_DIR = "memory/checkpoints"
AUDIO_OUT_DIR = "outputs/audio"
VIDEO_OUT_DIR = "outputs/video"
RAW_SCENES_DIR = "outputs/raw_scenes"
LOGS_DIR = "outputs/logs"

# Ensure directories exist upon import
for directory in [CHECKPOINT_DIR, AUDIO_OUT_DIR, VIDEO_OUT_DIR, RAW_SCENES_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)