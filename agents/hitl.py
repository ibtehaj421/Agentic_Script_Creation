from langgraph.types import interrupt

async def hitl_agent(state: dict) -> dict:
    import json
    script_preview = json.dumps(state["script"], indent=2)[:1000]

    decision = interrupt({
        "message": "Review the generated script. Approve to continue.",
        "preview": script_preview
    })

    # Command(resume={"approved": True/False}) lands here as the decision value
    if isinstance(decision, dict):
        approved = decision.get("approved", False)
    else:
        approved = bool(decision)

    return {
        "hitl_approved": approved,
        "errors": [] if approved else ["User rejected the script"]
    }