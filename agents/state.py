"""Shared LangGraph state schema for Phase 1."""
from __future__ import annotations

from typing import Any, Literal, TypedDict


class PipelineState(TypedDict, total=False):
    input_mode: Literal["manual", "auto"]
    raw_input: str
    num_scenes: int
    script: dict[str, Any]
    characters: list[dict[str, Any]]
    images: list[dict[str, Any]]
    validation_status: str
    hitl_approved: bool
    errors: list[str]
    status: str
    log: list[str]
