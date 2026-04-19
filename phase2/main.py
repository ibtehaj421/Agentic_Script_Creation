import json
from graph.studio_graph import app
from state.studio_state import StudioState
import config # Importing this will now handle all directory creation automatically

with open("scene_manifest.json") as f:
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

if __name__ == "__main__":
    print("🎬 Initializing The Studio Floor Pipeline...")
    result = app.invoke(initial_state)

    print("\n=== Final Outputs ===")
    for scene_id, path in result.get("final_outputs", {}).items():
        print(f"  {scene_id}: {path}")

    if result.get("errors"):
        print("\n=== Errors ===")
        for err in result["errors"]:
            print(f"  {err}")