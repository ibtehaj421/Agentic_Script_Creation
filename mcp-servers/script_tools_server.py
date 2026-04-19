import asyncio
import json
import re
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
import asyncpg

app = Server("script-tools")

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="generate_script_segment",
            description="Generate a structured multi-scene screenplay from a prompt",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt":     {"type": "string"},
                    "num_scenes": {"type": "integer"}
                },
                "required": ["prompt", "num_scenes"]
            }
        ),
        types.Tool(
            name="commit_memory",
            description="Store a key-value record in vector memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "key":  {"type": "string"},
                    "data": {"type": "object"}
                },
                "required": ["key", "data"]
            }
        )
    ]

async def _llm_call(prompt: str, system: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "groq")

    if provider == "groq":
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        def _call():
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL"),
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt}
                ]
            )
            return response.choices[0].message.content

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)

    else:  # ollama
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{os.getenv('OLLAMA_BASE_URL')}/api/chat",
                json={
                    "model": os.getenv("OLLAMA_MODEL"),
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": prompt}
                    ],
                    "stream": False
                }
            )
            return r.json()["message"]["content"]

async def _get_embedding(text: str) -> list:
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{os.getenv('OLLAMA_BASE_URL')}/api/embeddings",
            json={"model": os.getenv("EMBED_MODEL", "nomic-embed-text"), "prompt": text}
        )
        return r.json()["embedding"]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "generate_script_segment":
        prompt     = arguments["prompt"]
        num_scenes = arguments["num_scenes"]

        system = """You are a screenplay writer. Output ONLY raw JSON, no explanation, no markdown, no backticks.
Start your response with { and end with }.

Required format:
{
  "scenes": [
    {
      "scene_id": 1,
      "location": "string",
      "characters": ["string"],
      "dialogue": [
        {
          "speaker": "string",
          "line": "string",
          "visual_cue": "string"
        }
      ],
      "action": "string"
    }
  ]
}"""

        result = await _llm_call(
            f"Write a {num_scenes}-scene screenplay about: {prompt}",
            system
        )

        result = re.sub(r"```(?:json)?", "", result).strip()
        return [types.TextContent(type="text", text=result)]

    if name == "commit_memory":
        key       = arguments["key"]
        data      = arguments["data"]
        embedding = await _get_embedding(json.dumps(data))

        conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
        await conn.execute(
            "INSERT INTO memory (key, embedding, data) VALUES ($1, $2::vector, $3)",
            key, str(embedding), json.dumps(data)
        )
        await conn.close()

        return [types.TextContent(type="text", text=f"committed: {key}")]

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())