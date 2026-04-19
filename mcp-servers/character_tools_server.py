import asyncio
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from config import llm_call, get_embedding
import asyncpg

app = Server("character-tools")

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="extract_characters",
            description="Extract and formalize character identities from a script",
            inputSchema={
                "type": "object",
                "properties": {
                    "script": {"type": "object"}
                },
                "required": ["script"]
            }
        ),
        types.Tool(
            name="query_memory",
            description="Retrieve similar records from vector memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k":     {"type": "integer"}
                },
                "required": ["query"]
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

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "extract_characters":
        script = arguments["script"]

        system = """You are a character designer.
Given a screenplay, extract all characters and output ONLY valid JSON:
{
  "characters": [
    {
      "name": "...",
      "personality_traits": ["..."],
      "appearance": "...",
      "reference_style": "..."
    }
  ]
}"""

        result = await llm_call(json.dumps(script), system)
        result = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return [types.TextContent(type="text", text=result)]

    if name == "query_memory":
        query = arguments["query"]
        k     = arguments.get("k", 5)

        embedding = await get_embedding(query)

        conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
        rows = await conn.fetch(
            "SELECT key, data FROM match_memory($1::vector, $2)",
            str(embedding), k
        )
        await conn.close()

        result = [{"key": r["key"], "data": json.loads(r["data"])} for r in rows]
        return [types.TextContent(type="text", text=json.dumps(result))]

    if name == "commit_memory":
        key  = arguments["key"]
        data = arguments["data"]
        text = json.dumps(data)

        embedding = await get_embedding(text)

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