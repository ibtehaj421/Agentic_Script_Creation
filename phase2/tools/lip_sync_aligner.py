import subprocess
import os
from config import WAV2LIP_CHECKPOINT_PATH, RAW_SCENES_DIR

def lip_sync_aligner(swapped_video_path: str, audio_path: str, scene_id: int) -> str:
    """
    MCP Tool: Frame-by-frame alignment of audio waveform to lip motion using Wav2Lip.
    """
    output_path = os.path.join(RAW_SCENES_DIR, f"scene_{scene_id:02d}.mp4")
    
    if not os.path.exists(WAV2LIP_CHECKPOINT_PATH):
        raise FileNotFoundError(f"Wav2Lip checkpoint missing at {WAV2LIP_CHECKPOINT_PATH}")

    # Wav2Lip CLI Command
    cmd = [
        "python", "Wav2Lip/inference.py",
        "--checkpoint_path", WAV2LIP_CHECKPOINT_PATH,
        "--face", swapped_video_path,
        "--audio", audio_path,
        "--outfile", output_path,
        "--pads", "0", "20", "0", "0" # slight padding for better chin sync
    ]
    
    subprocess.run(" ".join(cmd), shell=True, check=True)
    return output_path