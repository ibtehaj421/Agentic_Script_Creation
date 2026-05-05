"""LangGraph state for the orchestrator — thin wrapper around PipelineState
so graph nodes can pass it as a dict."""
from __future__ import annotations

from typing import TypedDict


class OrchState(TypedDict, total=False):
    job_id: str
    pipeline_state: dict  # serialised PipelineState
