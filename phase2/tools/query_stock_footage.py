import requests
import os
from config import PEXELS_API_KEY, VIDEO_OUT_DIR

def query_stock_footage(location: str, visual_cue: str, action: str) -> str:
    """
    MCP Tool: Retrieves base video for a scene using Pexels API.
    """
    if not PEXELS_API_KEY:
        raise ValueError("PEXELS_API_KEY is missing from .env file")

    # Combine cues for the search query
    query = f"{location} {visual_cue}".replace(" ", "%20")
    output_path = os.path.join(VIDEO_OUT_DIR, f"raw_{abs(hash(query))}.mp4")
    
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=1&orientation=landscape"
    
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        data = res.json()
        if data.get("videos"):
            # Get the highest quality video link
            video_files = data["videos"][0]["video_files"]
            hd_files = [f for f in video_files if f["quality"] == "hd"]
            target_file = hd_files[0] if hd_files else video_files[0]
            
            video_data = requests.get(target_file["link"]).content
            with open(output_path, "wb") as f:
                f.write(video_data)
            return output_path
            
    raise Exception(f"Failed to retrieve footage. Status: {res.status_code}")