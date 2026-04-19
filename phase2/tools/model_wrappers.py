import subprocess
import requests
import os

def voice_cloning_synthesizer(speaker: str, line: str, emotion: str) -> str:
    """Uses local Coqui TTS (XTTS-v2) for zero-shot voice cloning."""
    voice_profiles = {
        "Detective Kael": "phase1/profiles/kael_voice_ref.wav",
        "Shadow Contact": "phase1/profiles/shadow_voice_ref.wav",
        "AI Core Unit":   "phase1/profiles/ai_core_voice_ref.wav"
    }
    ref_audio = voice_profiles.get(speaker, "phase1/profiles/default.wav")
    output_path = f"outputs/audio/{speaker.replace(' ', '_')}_{hash(line)}.wav"
    
    # Coqui TTS CLI subprocess
    cmd = [
        "tts", "--text", f'"{line}"', 
        "--model_name", "tts_models/multilingual/multi-dataset/xtts_v2",
        "--speaker_wav", ref_audio, 
        "--language_idx", "en", 
        "--out_path", output_path
    ]
    subprocess.run(" ".join(cmd), shell=True)
    return output_path

def query_stock_footage(location: str, visual_cue: str, action: str) -> str:
    """Uses Pexels API (Free) for high-utility video retrieval."""
    query = f"{location} {visual_cue}".replace(" ", "%20")
    api_key = os.getenv("PEXELS_API_KEY", "YOUR_FREE_KEY")
    output_path = f"outputs/raw_scenes/raw_scene_{hash(query)}.mp4"
    
    headers = {"Authorization": api_key}
    res = requests.get(f"https://api.pexels.com/videos/search?query={query}&per_page=1", headers=headers)
    
    if res.status_code == 200 and res.json()["videos"]:
        video_url = res.json()["videos"][0]["video_files"][0]["link"]
        video_data = requests.get(video_url).content
        with open(output_path, "wb") as f:
            f.write(video_data)
    return output_path

def identity_validator(character_name: str, character_image_path: str) -> bool:
    """Basic validation hook before face swap."""
    return os.path.exists(character_image_path)

def face_swapper(character_image_path: str, raw_video_path: str) -> str:
    """Uses InsightFace/Roop via subprocess for fast local face mapping."""
    output_path = raw_video_path.replace("raw_", "swapped_")
    cmd = [
        "python", "roop/run.py", 
        "-s", character_image_path, 
        "-t", raw_video_path, 
        "-o", output_path, 
        "--keep-fps"
    ]
    subprocess.run(" ".join(cmd), shell=True)
    return output_path

def lip_sync_aligner(swapped_video_path: str, audio_path: str, scene_id: int) -> str:
    """Uses Wav2Lip for temporal alignment."""
    output_path = f"outputs/raw_scenes/scene_{scene_id:02d}.mp4"
    cmd = [
        "python", "Wav2Lip/inference.py",
        "--checkpoint_path", "Wav2Lip/checkpoints/wav2lip_gan.pth",
        "--face", swapped_video_path,
        "--audio", audio_path,
        "--outfile", output_path
    ]
    subprocess.run(" ".join(cmd), shell=True)
    return output_path