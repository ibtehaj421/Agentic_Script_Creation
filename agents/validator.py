import json
from memory.store import script_session

def _validate_structure(script_text: str) -> tuple[bool, list[str]]:
    errors = []
    try:
        data = json.loads(script_text)
    except json.JSONDecodeError:
        return False, ["Invalid JSON"]

    scenes = data.get("scenes", [])
    if not scenes:
        errors.append("No scenes found")

    for i, scene in enumerate(scenes):
        if "location" not in scene:
            errors.append(f"Scene {i+1}: missing location")
        if "characters" not in scene:
            errors.append(f"Scene {i+1}: missing characters")
        if "dialogue" not in scene:
            errors.append(f"Scene {i+1}: missing dialogue")
        else:
            for d in scene["dialogue"]:
                if "speaker" not in d:
                    errors.append(f"Scene {i+1}: dialogue missing speaker")
                if "line" not in d:
                    errors.append(f"Scene {i+1}: dialogue missing line")
        if "action" not in scene:
            errors.append(f"Scene {i+1}: missing action")

    return len(errors) == 0, errors

async def validator_agent(state: dict) -> dict:
    raw_script = state["raw_input"]

    passed, errors = _validate_structure(raw_script)

    if not passed:
        return {
            "validation_status": "failed",
            "errors": errors,
            "script": {}
        }

    script = json.loads(raw_script)

    async with script_session() as session:
        await session.call_tool(
            "commit_memory",
            {"key": "script:latest", "data": script}
        )

    return {
        "validation_status": "passed",
        "script": script,
        "errors": []
    }