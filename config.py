import os
from dotenv import load_dotenv
import httpx
load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
DATABASE_URL  = os.getenv("DATABASE_URL")
EMBED_MODEL   = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM     = int(os.getenv("EMBED_DIM", 768))

async def llm_call(prompt: str, system: str = "",require_json: bool = False) -> str:
    if LLM_PROVIDER == "groq":
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt}
            ],
            response_format={"type": "json_object"} if require_json else {"type": "text"}
        )
        return response.choices[0].message.content

    else:  # ollama
        
        # async with httpx.AsyncClient() as client:
        #     r = await client.post(
        #         f"{os.getenv('OLLAMA_BASE_URL')}/api/chat",
        #         json={
        #             "model": os.getenv("OLLAMA_MODEL"),
        #             "messages": [
        #                 {"role": "system", "content": system},
        #                 {"role": "user",   "content": prompt}
        #             ],
        #             "stream": False
        #         }
        #     )
        #     return r.json()["message"]["content"]
        payload = {
        "model": os.getenv("OLLAMA_MODEL"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ],
        "stream": False
    }

        # Force strict JSON output if requested by the agent
        if require_json:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{os.getenv('OLLAMA_BASE_URL')}/api/chat",
                json=payload
            )
            r.raise_for_status()  
            return r.json()["message"]["content"]
async def get_embedding(text: str) -> list[float]:
    import httpx
    # nomic-embed-text via ollama regardless of LLM provider
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{os.getenv('OLLAMA_BASE_URL')}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text}
        )
        return r.json()["embedding"]