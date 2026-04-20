"""Human-in-the-Loop Agent.

Role:   Provide a checkpoint control before expensive downstream work.
Why:    Prevents hallucinated scripts from advancing and ensures user
        intent alignment.

Uses LangGraph's `interrupt` primitive — the graph pauses here and
`main.py` resumes with `Command(resume={"approved": bool})`.
"""
from __future__ import annotations

import json
from typing import Any

from langgraph.types import interrupt


async def hitl_agent(state: dict[str, Any]) -> dict[str, Any]:
    preview = json.dumps(state.get("script", {}), indent=2)[:1000]

    decision = interrupt(
        {
            "message": "Review the generated script. Approve to continue.",
            "preview": preview,
        }
    )

    if isinstance(decision, dict):
        approved = bool(decision.get("approved", False))
    else:
        approved = bool(decision)

    log = state.get("log", []) + [f"[hitl] approved={approved}"]
    return {
        "hitl_approved": approved,
        "errors": [] if approved else ["User rejected the script"],
        "log": log,
    }
