"""Validate an arbitrary LLM-JSON blob against a Pydantic model."""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel, ValidationError

from mcp.base_tool import BaseTool, ToolSpec


class JsonStructurerTool(BaseTool):
    spec = ToolSpec(
        name="validate_json_schema",
        description="Validate a dict against a Pydantic model. Returns {ok, errors, normalized}.",
        category="llm",
    )

    def run(self, data: dict, model: Type[BaseModel] | None = None) -> dict[str, Any]:
        if model is None:
            return {"ok": True, "errors": [], "normalized": data}
        try:
            normalized = model(**data)
            return {"ok": True, "errors": [], "normalized": normalized.model_dump()}
        except ValidationError as e:
            return {"ok": False, "errors": [err["msg"] for err in e.errors()], "normalized": None}
