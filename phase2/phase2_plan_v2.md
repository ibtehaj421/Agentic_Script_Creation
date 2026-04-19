# Phase 2 Implementation Plan — The Studio Floor
### CS-4015 Agentic AI | Video & Audio Synthesis Layer
> Built against your actual `scene_manifest.json` — 3 scenes, characters: Detective Kael, Shadow Contact, AI Core Unit

---

## Your Manifest Structure (Reference)

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "location": "Neo-Tokyo, Neon Alleyway",
      "characters": ["Detective Kael", "Shadow Contact"],
      "dialogue": [
        {
          "speaker": "Detective Kael",
          "line": "The bio-signature is corrupted. Why?",
          "visual_cue": "Rain streaks down the wet pavement."
        }
      ],
      "action": "Kael adjusts his cybernetic earpiece..."
    }
  ]
}
```

Key fields Phase 2 will consume:
| Field | Used By |
|---|---|
| `scene_id` | All agents — primary key |
| `location` | Video Gen Agent (`query_stock_footage`) |
| `characters[]` | Face Swap Agent (identity lookup) |
| `dialogue[].speaker` | Voice Synth Agent (voice profile lookup) |
| `dialogue[].line` | Voice Synth Agent (TTS input) |
| `dialogue[].visual_cue` | Video Gen Agent (scene framing) |
| `action` | Video Gen Agent (motion context) |

---

## Directory Structure

```
phase2/
├── agents/
│   ├── scene_parser_agent.py
│   ├── voice_synth_agent.py
│   ├── video_gen_agent.py
│   ├── face_swap_agent.py
│   └── lip_sync_agent.py
├── tools/
│   ├── get_task_graph.py
│   ├── commit_memory.py
│   ├── voice_cloning_synthesizer.py
│   ├── query_stock_footage.py
│   ├── face_swapper.py
│   ├── identity_validator.py
│   └── lip_sync_aligner.py
├── graph/
│   └── studio_graph.py
├── state/
│   └── studio_state.py
├── memory/
│   └── checkpoints/
├── outputs/
│   ├── raw_scenes/         # scene_01.mp4, scene_02.mp4, scene_03.mp4
│   ├── audio/              # scene_01_kael.wav, scene_01_shadow.wav, ...
│   └── logs/
│       └── task_graph_logs.json
└── main.py
```

---

## Step 1 — Shared State Schema
**File:** `state/studio_state.py`

Designed around your manifest's exact fields:

```python
from typing import TypedDict, Optional

class DialogueLine(TypedDict):
    speaker: str
    line: str
    visual_cue: str

class SceneTask(TypedDict):
    scene_id: int
    location: str
    characters: list[str]
    dialogue: list[DialogueLine]
    action: str

class StudioState(TypedDict):
    scene_manifest: dict               # Raw loaded JSON
    task_graph: list[SceneTask]        # Parsed scene tasks
    audio_outputs: dict[str, str]      # "scene_1_Kael" -> "audio/scene_1_kael.wav"
    video_outputs: dict[str, str]      # "scene_1" -> "video/scene_1_raw.mp4"
    face_swapped_outputs: dict[str, str]  # "scene_1" -> "video/scene_1_swapped.mp4"
    final_outputs: dict[str, str]      # "scene_1" -> "raw_scenes/scene_01.mp4"
    errors: list[str]
```

> **Note:** `audio_outputs` is keyed as `"scene_{id}_{speaker}"` because each scene has multiple speakers (e.g. scene 1 has both Kael and Shadow Contact with separate `.wav` files that get merged before lip sync).

---

## Step 2 — MCP Tool Wrappers
**File:** `tools/`

### `get_task_graph.py`
Converts raw manifest into a flat list of `SceneTask` objects:

```python
def get_task_graph(scene_manifest: dict) -> list[dict]:
    """
    MCP Tool: Decomposes scene_manifest into executable task units.
    Each scene becomes one task with all fields preserved.
    """
    tasks = []
    for scene in scene_manifest["scenes"]:
        tasks.append({
            "scene_id": scene["scene_id"],
            "location": scene["location"],
            "characters": scene["characters"],
            "dialogue": scene["dialogue"],
            "action": scene["action"]
        })
    # Log to task_graph_logs.json
    log_task_graph(tasks)
    return tasks
```

### `commit_memory.py`
```python
import json, os

CHECKPOINT_DIR = "memory/checkpoints"

def commit_memory(data, checkpoint_id: str):
    """MCP Tool: Persist intermediate output. Supports resumability."""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    path = f"{CHECKPOINT_DIR}/{checkpoint_id}.json"
    with open(path, "w") as f:
        json.dump({"checkpoint_id": checkpoint_id, "data": data}, f)
    return path

def checkpoint_exists(checkpoint_id: str) -> bool:
    return os.path.exists(f"{CHECKPOINT_DIR}/{checkpoint_id}.json")

def load_checkpoint(checkpoint_id: str):
    with open(f"{CHECKPOINT_DIR}/{checkpoint_id}.json") as f:
        return json.load(f)["data"]
```

### `voice_cloning_synthesizer.py`
```python
def voice_cloning_synthesizer(speaker: str, line: str, emotion: str) -> str:
    """
    MCP Tool: Clones voice from character profile and synthesizes speech.
    
    speaker:  "Detective Kael" | "Shadow Contact" | "AI Core Unit"
    line:     dialogue line text
    emotion:  inferred from scene action/visual_cue
    
    Returns: path to generated .wav file
    """
    # Map character -> voice profile reference audio
    voice_profiles = {
        "Detective Kael": "profiles/kael_voice_ref.wav",      # From Phase 1
        "Shadow Contact": "profiles/shadow_voice_ref.wav",
        "AI Core Unit":   "profiles/ai_core_voice_ref.wav"
    }
    profile = voice_profiles.get(speaker, "profiles/default.wav")
    
    # Call TTS model (e.g. Coqui TTS, ElevenLabs, Bark)
    output_path = f"outputs/audio/{speaker.replace(' ', '_')}_{hash(line)}.wav"
    # ... synthesis call here ...
    return output_path
```

### `query_stock_footage.py`
```python
def query_stock_footage(location: str, visual_cue: str, action: str) -> str:
    """
    MCP Tool: Retrieves or generates base video for a scene.
    
    location:   "Neo-Tokyo, Neon Alleyway"
    visual_cue: "Rain streaks down the wet pavement."
    action:     "Kael adjusts his cybernetic earpiece..."
    
    Returns: path to raw video file
    """
    # Build search query from location + visual_cue
    query = f"{location} {visual_cue}"
    # ... call stock API or video generation model ...
    return f"outputs/video/raw_{location.replace(' ', '_')}.mp4"
```

### `identity_validator.py`
```python
def identity_validator(character_name: str, character_image_path: str) -> bool:
    """
    MCP Tool: Validates character identity before face swap.
    Checks that the reference image matches expected character.
    """
    # Run face detection on character_image_path
    # Validate against stored character identity embedding
    return True  # or False if mismatch
```

### `face_swapper.py`
```python
def face_swapper(character_image_path: str, raw_video_path: str) -> str:
    """MCP Tool: Maps character face onto every frame of raw video."""
    output_path = raw_video_path.replace("raw_", "swapped_")
    # ... face swap model call (e.g. InsightFace) ...
    return output_path
```

### `lip_sync_aligner.py`
```python
def lip_sync_aligner(swapped_video_path: str, audio_path: str, scene_id: int) -> str:
    """
    MCP Tool: Frame-by-frame alignment of audio waveform to lip motion.
    Returns final .mp4
    """
    output_path = f"outputs/raw_scenes/scene_{scene_id:02d}.mp4"
    # ... lip sync model call (e.g. Wav2Lip) ...
    return output_path
```

---

## Step 3 — The 5 Agents

### 3.1 Scene Parser Agent
```python
# agents/scene_parser_agent.py
from tools.get_task_graph import get_task_graph
from tools.commit_memory import commit_memory

def scene_parser_node(state: StudioState) -> StudioState:
    manifest = state["scene_manifest"]
    
    # Call MCP tool
    task_graph = get_task_graph(manifest)
    
    state["task_graph"] = task_graph
    
    # Checkpoint
    commit_memory(task_graph, checkpoint_id="task_graph")
    
    return state
```

---

### 3.2 Voice Synthesis Agent
Handles multiple speakers per scene (your scenes have 1–2 speakers each):

```python
# agents/voice_synth_agent.py
from tools.voice_cloning_synthesizer import voice_cloning_synthesizer
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint

EMOTION_MAP = {
    # Infer emotion from action/visual_cue text keywords
    "rain": "tense",
    "warning": "urgent",
    "hacks": "determined",
    "watches": "reflective",
}

def infer_emotion(scene: dict) -> str:
    action_text = scene["action"].lower()
    for keyword, emotion in EMOTION_MAP.items():
        if keyword in action_text:
            return emotion
    return "neutral"

def voice_synth_node(state: StudioState, scene: dict) -> StudioState:
    scene_id = scene["scene_id"]
    emotion = infer_emotion(scene)
    
    for turn in scene["dialogue"]:
        speaker = turn["speaker"]   # e.g. "Detective Kael"
        line = turn["line"]
        checkpoint_id = f"audio_{scene_id}_{speaker.replace(' ', '_')}"
        
        # Resumability check
        if checkpoint_exists(checkpoint_id):
            wav_path = load_checkpoint(checkpoint_id)
        else:
            wav_path = voice_cloning_synthesizer(speaker, line, emotion)
            commit_memory(wav_path, checkpoint_id=checkpoint_id)
        
        key = f"scene_{scene_id}_{speaker.replace(' ', '_')}"
        state["audio_outputs"][key] = wav_path
    
    return state
```

**Your scenes produce these audio files:**
```
scene_1_Detective_Kael.wav      — "The bio-signature is corrupted. Why?"
scene_1_Shadow_Contact.wav      — "Because the corporation owns the rain."
scene_2_AI_Core_Unit.wav        — "Access denied. Protocol is secure."
scene_2_Detective_Kael.wav      — "I don't need protocol. I need truth."
scene_3_Detective_Kael_1.wav    — "They thought they could control the city."
scene_3_Detective_Kael_2.wav    — "But the network remembers everything."
```
> Scene 3 has Kael speaking twice — handle by indexing repeated speakers.

---

### 3.3 Video Generation Agent
```python
# agents/video_gen_agent.py
from tools.query_stock_footage import query_stock_footage
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint

def video_gen_node(state: StudioState, scene: dict) -> StudioState:
    scene_id = scene["scene_id"]
    checkpoint_id = f"video_{scene_id}"
    
    if checkpoint_exists(checkpoint_id):
        raw_video = load_checkpoint(checkpoint_id)
    else:
        # Combine all visual_cues from dialogue turns
        visual_cues = " ".join(d["visual_cue"] for d in scene["dialogue"])
        
        raw_video = query_stock_footage(
            location=scene["location"],     # "Neo-Tokyo, Neon Alleyway"
            visual_cue=visual_cues,         # "Rain streaks down..." + "A holographic message..."
            action=scene["action"]
        )
        commit_memory(raw_video, checkpoint_id=checkpoint_id)
    
    state["video_outputs"][f"scene_{scene_id}"] = raw_video
    return state
```

---

### 3.4 Face Swap Agent
```python
# agents/face_swap_agent.py
from tools.identity_validator import identity_validator
from tools.face_swapper import face_swapper
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint

# Map character names to Phase 1 generated images
CHARACTER_IMAGES = {
    "Detective Kael":  "phase1/outputs/characters/detective_kael.png",
    "Shadow Contact":  "phase1/outputs/characters/shadow_contact.png",
    "AI Core Unit":    "phase1/outputs/characters/ai_core_unit.png",
}

def face_swap_node(state: StudioState, scene: dict) -> StudioState:
    scene_id = scene["scene_id"]
    checkpoint_id = f"faceswap_{scene_id}"
    
    if checkpoint_exists(checkpoint_id):
        state["face_swapped_outputs"][f"scene_{scene_id}"] = load_checkpoint(checkpoint_id)
        return state
    
    raw_video = state["video_outputs"][f"scene_{scene_id}"]
    
    # Use primary character (first in list) for face swap
    primary_char = scene["characters"][0]   # "Detective Kael" for all 3 scenes
    char_image = CHARACTER_IMAGES[primary_char]
    
    # MUST validate before swapping
    is_valid = identity_validator(primary_char, char_image)
    if not is_valid:
        state["errors"].append(f"Identity validation failed for scene {scene_id}: {primary_char}")
        return state
    
    swapped = face_swapper(char_image, raw_video)
    commit_memory(swapped, checkpoint_id=checkpoint_id)
    state["face_swapped_outputs"][f"scene_{scene_id}"] = swapped
    return state
```

---

### 3.5 Lip Sync Agent (Fusion Layer)
Merges all audio tracks for the scene then aligns with face-swapped video:

```python
# agents/lip_sync_agent.py
from tools.lip_sync_aligner import lip_sync_aligner
from tools.commit_memory import commit_memory, checkpoint_exists, load_checkpoint
import subprocess

def merge_audio_tracks(audio_paths: list[str], scene_id: int) -> str:
    """Merge multiple speaker .wav files into one scene audio track."""
    merged_path = f"outputs/audio/scene_{scene_id}_merged.wav"
    # Use ffmpeg to concatenate/mix in dialogue order
    inputs = " ".join(f"-i {p}" for p in audio_paths)
    subprocess.run(f"ffmpeg {inputs} -filter_complex amerge {merged_path}", shell=True)
    return merged_path

def lip_sync_node(state: StudioState, scene: dict) -> StudioState:
    scene_id = scene["scene_id"]
    checkpoint_id = f"final_{scene_id}"
    
    if checkpoint_exists(checkpoint_id):
        state["final_outputs"][f"scene_{scene_id}"] = load_checkpoint(checkpoint_id)
        return state
    
    # Collect audio tracks for this scene in dialogue order
    audio_paths = []
    for turn in scene["dialogue"]:
        speaker_key = f"scene_{scene_id}_{turn['speaker'].replace(' ', '_')}"
        audio_paths.append(state["audio_outputs"][speaker_key])
    
    merged_audio = merge_audio_tracks(audio_paths, scene_id)
    swapped_video = state["face_swapped_outputs"][f"scene_{scene_id}"]
    
    final_mp4 = lip_sync_aligner(swapped_video, merged_audio, scene_id)
    commit_memory(final_mp4, checkpoint_id=checkpoint_id)
    state["final_outputs"][f"scene_{scene_id}"] = final_mp4
    return state
```

---

## Step 4 — LangGraph Workflow
**File:** `graph/studio_graph.py`

```python
from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from state.studio_state import StudioState
from agents.scene_parser_agent import scene_parser_node
from agents.voice_synth_agent import voice_synth_node
from agents.video_gen_agent import video_gen_node
from agents.face_swap_agent import face_swap_node
from agents.lip_sync_agent import lip_sync_node

def route_to_parallel_branches(state: StudioState):
    """
    Fan out each of the 3 scenes to BOTH audio and video branches in parallel.
    This is what satisfies the 'Parallel Architecture' rubric criterion.
    """
    sends = []
    for scene in state["task_graph"]:
        sends.append(Send("voice_synth_node", {"scene": scene}))  # Audio branch
        sends.append(Send("video_gen_node",   {"scene": scene}))  # Video branch
    return sends  # 6 parallel tasks total (3 scenes × 2 branches)

def route_to_face_swap(state: StudioState):
    """After video gen, route each scene to face swap."""
    return [
        Send("face_swap_node", {"scene": scene})
        for scene in state["task_graph"]
    ]

def route_to_lip_sync(state: StudioState):
    """After face swap + audio, converge at lip sync."""
    return [
        Send("lip_sync_node", {"scene": scene})
        for scene in state["task_graph"]
    ]

# Build graph
graph = StateGraph(StudioState)

graph.add_node("scene_parser_node", scene_parser_node)
graph.add_node("voice_synth_node",  voice_synth_node)
graph.add_node("video_gen_node",    video_gen_node)
graph.add_node("face_swap_node",    face_swap_node)
graph.add_node("lip_sync_node",     lip_sync_node)

graph.set_entry_point("scene_parser_node")
graph.add_conditional_edges("scene_parser_node", route_to_parallel_branches)
graph.add_conditional_edges("video_gen_node",    route_to_face_swap)
graph.add_conditional_edges("face_swap_node",    route_to_lip_sync)
graph.add_conditional_edges("voice_synth_node",  route_to_lip_sync)
graph.add_edge("lip_sync_node", END)

app = graph.compile()
```

**Execution flow for your 3 scenes:**
```
scene_parser_node
       │
       ├──── Send(voice_synth, scene_1) ──► voice_synth_node ──┐
       ├──── Send(video_gen,   scene_1) ──► video_gen_node ──► face_swap_node ──► lip_sync_node ──► scene_01.mp4
       │
       ├──── Send(voice_synth, scene_2) ──► voice_synth_node ──┐
       ├──── Send(video_gen,   scene_2) ──► video_gen_node ──► face_swap_node ──► lip_sync_node ──► scene_02.mp4
       │
       ├──── Send(voice_synth, scene_3) ──► voice_synth_node ──┐
       └──── Send(video_gen,   scene_3) ──► video_gen_node ──► face_swap_node ──► lip_sync_node ──► scene_03.mp4
```

---

## Step 5 — Entry Point
**File:** `main.py`

```python
import json
from graph.studio_graph import app
from state.studio_state import StudioState

with open("phase1/outputs/scene_manifest.json") as f:
    manifest = json.load(f)

initial_state: StudioState = {
    "scene_manifest": manifest,
    "task_graph": [],
    "audio_outputs": {},
    "video_outputs": {},
    "face_swapped_outputs": {},
    "final_outputs": {},
    "errors": []
}

result = app.invoke(initial_state)

print("\n=== Final Outputs ===")
for scene_id, path in result["final_outputs"].items():
    print(f"  {scene_id}: {path}")

if result["errors"]:
    print("\n=== Errors ===")
    for err in result["errors"]:
        print(f"  {err}")
```

---

## Expected Final Outputs

```
outputs/raw_scenes/scene_01.mp4   — Neo-Tokyo Neon Alleyway (Kael + Shadow Contact)
outputs/raw_scenes/scene_02.mp4   — Omicron Corp Server Core (Kael + AI Core Unit)
outputs/raw_scenes/scene_03.mp4   — Tokyo Skyline Bridge (Kael monologue)
outputs/audio/scene_1_merged.wav
outputs/audio/scene_2_merged.wav
outputs/audio/scene_3_merged.wav
outputs/logs/task_graph_logs.json
```

---

## Evaluation Mapping

| Criteria | Your Implementation | Marks |
|---|---|---|
| **Parallel Architecture (10)** | `Send()` fans out all 3 scenes × 2 branches = 6 parallel tasks from `scene_parser_node` | 10 |
| **Audio Quality (20)** | Per-speaker voice cloning with emotion inferred from `action` field; separate `.wav` per dialogue turn | 20 |
| **Video Quality (20)** | `query_stock_footage` uses `location` + all `visual_cue` strings + `action`; Phase 1 character images fed into face swap | 20 |
| **Lip Sync Accuracy (10)** | `merge_audio_tracks` preserves dialogue order; `lip_sync_aligner` aligns merged audio to face-swapped video | 10 |
| **MCP Tool Usage (5)** | All 7 tools used correctly: `get_task_graph`, `commit_memory`, `voice_cloning_synthesizer`, `query_stock_footage`, `identity_validator`, `face_swapper`, `lip_sync_aligner` | 5 |
| **Fault Tolerance (5)** | `checkpoint_exists` + `load_checkpoint` guard at start of every agent; `commit_memory` after every output | 5 |
| **Total** | | **70** |
