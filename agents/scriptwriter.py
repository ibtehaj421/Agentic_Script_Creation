import json
import re
from memory.store import script_session

async def scriptwriter_agent(state: dict) -> dict:
    prompt     = state["raw_input"]
    num_scenes = state.get("num_scenes", 3)

    async with script_session() as session:
        tools = await session.list_tools()
        tool_names = [t.name for t in tools.tools]
        assert "generate_script_segment" in tool_names

        result = await session.call_tool(
            "generate_script_segment",
            {"prompt": prompt, "num_scenes": num_scenes}
        )
        raw = result.content[0].text
        raw = re.sub(r"```(?:json)?", "", raw).strip()

        if not raw:
            raise ValueError("LLM returned empty response")

        script = json.loads(raw)

        await session.call_tool(
            "commit_memory",
            {"key": "script:latest", "data": script}
        )

    return {"script": script, "status": "script_ready"}