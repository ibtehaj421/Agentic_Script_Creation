import subprocess
import os
from config import ROOP_DIR, VIDEO_OUT_DIR

def face_swapper(character_image_path: str, raw_video_path: str) -> str:
    """
    MCP Tool: Maps character face onto video frames using Roop (InsightFace).
    """
    base_name = os.path.basename(raw_video_path).replace("raw_", "swapped_")
    output_path = os.path.join(VIDEO_OUT_DIR, base_name)
    
    run_script = os.path.join(ROOP_DIR, "run.py")
    
    if not os.path.exists(run_script):
        raise FileNotFoundError(f"Roop installation not found at {ROOP_DIR}")

    # Roop CLI Command
    cmd = [
        "python", run_script, 
        "-s", character_image_path, 
        "-t", raw_video_path, 
        "-o", output_path, 
        "--keep-fps",
        "--execution-provider", "cpu" # Change to "cuda" if you have an Nvidia GPU
    ]
    
    subprocess.run(" ".join(cmd), shell=True, check=True)
    return output_path