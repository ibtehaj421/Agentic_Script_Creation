from typing import TypedDict, Annotated
import operator

def merge_dicts(a: dict, b: dict) -> dict:
    """Safely merges dictionaries from parallel branches."""
    c = a.copy()
    c.update(b)
    return c

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
    scene_manifest: dict               
    task_graph: list[SceneTask]        
    
    # Annotated reducers tell LangGraph how to combine parallel outputs
    audio_outputs: Annotated[dict[str, str], merge_dicts]      
    video_outputs: Annotated[dict[str, str], merge_dicts]      
    face_swapped_outputs: Annotated[dict[str, str], merge_dicts]  
    final_outputs: Annotated[dict[str, str], merge_dicts]      
    errors: Annotated[list[str], operator.add]