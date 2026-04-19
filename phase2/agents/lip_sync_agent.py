import subprocess
import os
from state.studio_state import StudioState
from tools.lip_sync_aligner import lip_sync_aligner
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint
from config import AUDIO_OUT_DIR
import shutil
def merge_audio_tracks(audio_paths: list[str], scene_id: int) -> str:
    """Sequentially merges multiple dialogue lines using ffmpeg."""
    merged_path = os.path.join(AUDIO_OUT_DIR, f"scene_{scene_id}_merged.wav")
    
    # If there's only one line of dialogue in the scene, skip ffmpeg and just copy it
    if len(audio_paths) == 1:
        shutil.copy(audio_paths[0], merged_path)
        return merged_path
        
    # Build the ffmpeg concat string to play dialogue turn-by-turn
    inputs = " ".join(f'-i "{p}"' for p in audio_paths)
    filter_str = "".join(f"[{i}:a]" for i in range(len(audio_paths))) + f"concat=n={len(audio_paths)}:v=0:a=1[out]"
    
    cmd = f'ffmpeg {inputs} -filter_complex "{filter_str}" -map "[out]" "{merged_path}" -y'
    
    print(f"🔊 Merging dialogue audio for scene {scene_id}...")
    try:
        # check=True forces Python to crash and show us the error if ffmpeg fails
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg Merge Failed: {e.stderr.decode()}")
        raise e
        
    return merged_path

def lip_sync_node(payload: dict) -> dict:
    scene = payload["scene"]
    audio_outputs = payload["audio_outputs"]
    face_swapped_outputs = payload["face_swapped_outputs"]
    scene_id = scene["scene_id"]
    checkpoint_id = f"final_{scene_id}"
    
    if checkpoint_exists(checkpoint_id):
        return {"final_outputs": {f"scene_{scene_id}": load_checkpoint(checkpoint_id)}}
    
    audio_paths = []
    for turn in scene["dialogue"]:
        speaker_key = f"scene_{scene_id}_{turn['speaker'].replace(' ', '_')}"
        if speaker_key in audio_outputs:
            audio_paths.append(audio_outputs[speaker_key])
            
    if not audio_paths: return {}
            
    merged_audio = merge_audio_tracks(audio_paths, scene_id)
    swapped_video = face_swapped_outputs.get(f"scene_{scene_id}")
    
    if swapped_video and merged_audio:
        final_mp4 = lip_sync_aligner(swapped_video, merged_audio, scene_id)
        commit_memory(final_mp4, checkpoint_id=checkpoint_id)
        return {"final_outputs": {f"scene_{scene_id}": final_mp4}}
        
    return {}