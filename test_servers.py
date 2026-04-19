# test_mcp.py
import asyncio
from memory.store import script_session, character_session

async def test_script_server():
    async with script_session() as session:
        tools = await session.list_tools()
        print("script tools:", [t.name for t in tools.tools])

        result = await session.call_tool(
            "generate_script_segment",
            {"prompt": "two astronauts find an alien artifact", "num_scenes": 2}
        )
        print("script result:", result.content[0].text[:300])

async def test_character_server():
    async with character_session() as session:
        tools = await session.list_tools()
        print("character tools:", [t.name for t in tools.tools])

async def main():
    print("\n── Testing script server ──")
    await test_script_server()

    print("\n── Testing character server ──")
    await test_character_server()

asyncio.run(main())