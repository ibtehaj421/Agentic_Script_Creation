from state.studio_state import StudioState
from tools.voice_cloning_synthesizer import voice_cloning_synthesizer
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint

EMOTION_MAP = {"rain": "tense", "warning": "urgent", "hacks": "determined", "watches": "reflective"}

def infer_emotion(scene: dict) -> str:
    action_text = scene["action"].lower()
    for keyword, emotion in EMOTION_MAP.items():
        if keyword in action_text: return emotion
    return "neutral"

# Keep your imports and EMOTION_MAP / infer_emotion intact...

def voice_synth_node(payload: dict) -> dict:
    scene = payload["scene"]
    scene_id = scene["scene_id"]
    emotion = infer_emotion(scene)
    
    audio_updates = {}
    
    for turn in scene["dialogue"]:
        speaker = turn["speaker"]
        line = turn["line"]
        checkpoint_id = f"audio_{scene_id}_{speaker.replace(' ', '_')}"
        
        if checkpoint_exists(checkpoint_id):
            wav_path = load_checkpoint(checkpoint_id)
        else:
            wav_path = voice_cloning_synthesizer(speaker, line, emotion)
            commit_memory(wav_path, checkpoint_id=checkpoint_id)
            
        key = f"scene_{scene_id}_{speaker.replace(' ', '_')}"
        audio_updates[key] = wav_path
        
    return {"audio_outputs": audio_updates}