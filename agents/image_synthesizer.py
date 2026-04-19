# import httpx
# import base64
# import os
# import json
# from pathlib import Path
# import asyncio

# HF_TOKEN  = os.getenv("HF_TOKEN")
# HF_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
# OUT_DIR   = Path("outputs/images")

# async def image_synthesizer_agent(state: dict) -> dict:
#     OUT_DIR.mkdir(parents=True, exist_ok=True)
#     characters = state["characters"]
#     image_paths = []

#     async with httpx.AsyncClient(timeout=60) as client:
#         for char in characters:
#             prompt = f"Character portrait: {char['appearance']}, style: {char['reference_style']}, cinematic lighting"

            
#             for attempt in range(4):
#                 r = await client.post(
#                         HF_URL,
#                         headers={"Authorization": f"Bearer {HF_TOKEN}"},
#                         json={"inputs": prompt}
#                     )                                  
#                 if r.status_code == 200:
#                     break
#                 await asyncio.sleep(20)

#             if r.status_code == 200:
#                 path = OUT_DIR / f"{char['name'].replace(' ', '_')}.png"
#                 path.write_bytes(r.content)
#                 image_paths.append(str(path))
#             else:
#                 # non-blocking — log and continue
#                 print(f"Image gen failed for {char['name']}: {r.status_code}")

#     return {"images": image_paths, "status": "images_ready"}
import httpx
import os
from pathlib import Path
from PIL import Image, ImageDraw

HF_TOKEN = os.getenv("HF_TOKEN")
OUT_DIR  = Path("outputs/images")

HF_MODELS = [
    "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1",
    "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5",
]

async def image_synthesizer_agent(state: dict) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    characters = state["characters"]
    image_paths = []

    async with httpx.AsyncClient(timeout=60) as client:
        for char in characters:
            prompt = f"Character portrait: {char['appearance']}, style: {char['reference_style']}, cinematic lighting"
            path   = OUT_DIR / f"{char['name'].replace(' ', '_')}.png"
            saved  = False

            for url in HF_MODELS:
                r = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {HF_TOKEN}"},
                    json={"inputs": prompt}
                )
                if r.status_code == 200:
                    path.write_bytes(r.content)
                    image_paths.append(str(path))
                    saved = True
                    print(f"  ✓ image saved for {char['name']}")
                    break

            if not saved:
                # placeholder — pipeline always completes
                img  = Image.new("RGB", (512, 512), color=(20, 20, 40))
                draw = ImageDraw.Draw(img)
                draw.text((20, 20),  f"Name:   {char['name']}",                     fill=(255, 255, 255))
                draw.text((20, 60),  f"Look:   {char['appearance'][:60]}",           fill=(200, 200, 200))
                draw.text((20, 100), f"Style:  {char['reference_style'][:60]}",      fill=(200, 200, 200))
                draw.text((20, 140), f"Traits: {', '.join(char.get('personality_traits', []))[:60]}", fill=(180, 180, 220))
                img.save(path)
                image_paths.append(str(path))
                print(f"  ⚠ placeholder image created for {char['name']}")

    return {"images": image_paths, "status": "images_ready"}