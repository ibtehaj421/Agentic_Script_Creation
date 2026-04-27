"""Structured event logging that the backend WebSocket relays to the frontend.

Phases call `emit(job_id, phase, event_type, payload)` and the backend
subscribes via `with_event_sink` for that job_id.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

_LOGGERS: dict[str, logging.Logger] = {}
# job_id -> async queue used by the WebSocket
_EVENT_SINKS: dict[str, "asyncio.Queue[dict]"] = {}


def get_logger(name: str) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    lg = logging.getLogger(name)
    if not lg.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
        lg.addHandler(h)
    lg.setLevel(logging.INFO)
    _LOGGERS[name] = lg
    return lg


@contextmanager
def with_event_sink(job_id: str, queue: "asyncio.Queue[dict]"):
    """Register an event queue for the duration of a job run."""
    _EVENT_SINKS[job_id] = queue
    try:
        yield
    finally:
        _EVENT_SINKS.pop(job_id, None)


def emit(job_id: str, phase: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
    """Push a structured event. Logs to stdout and fans out to the WS sink if present."""
    msg = {
        "job_id": job_id,
        "phase": phase,
        "event": event_type,
        "data": payload or {},
    }
    get_logger(phase).info(f"{event_type} {payload or ''}")
    q = _EVENT_SINKS.get(job_id)
    if q is not None:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            # Drop events rather than block the pipeline
            pass
