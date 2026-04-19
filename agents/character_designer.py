import json
from memory.store import character_session

async def character_designer_agent(state: dict) -> dict:
    script = state["script"]

    async with character_session() as session:
        tools = await session.list_tools()
        tool_names = [t.name for t in tools.tools]
        assert "extract_characters" in tool_names

        result = await session.call_tool(
            "extract_characters",
            {"script": script}
        )
        raw = result.content[0].text
        characters = json.loads(raw)["characters"]

        # commit each character to memory
        for char in characters:
            await session.call_tool(
                "commit_memory",
                {"key": f"character:{char['name']}", "data": char}
            )

    return {"characters": characters, "status": "characters_ready"}