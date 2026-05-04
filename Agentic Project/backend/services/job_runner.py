"""In-process job manager.

For a single-user demo we don't need Celery/Redis — just an asyncio
task-per-job approach. Each job gets:
    * its own event queue (consumed by the WebSocket)
    * a Future tracking completion
    * a lookup to the latest PipelineState

This matches the spec's "real-time, phase-aware full-stack web application"
requirement without the operational cost of a distributed queue.
"""
from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from shared.utils import with_event_sink

# A job's event queue
_QUEUES: Dict[str, asyncio.Queue] = {}
_JOBS: Dict[str, "JobHandle"] = {}
_LOCK = threading.Lock()


@dataclass
class JobHandle:
    job_id: str
    title: str = ""
    status: str = "pending"  # pending | running | done | failed
    error: str = ""
    result: Optional[dict] = None
    event_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=5000))
    task: Optional[asyncio.Task] = None


def new_job_id() -> str:
    return "job_" + uuid.uuid4().hex[:10]


def register_job(job_id: str, title: str = "") -> JobHandle:
    with _LOCK:
        handle = JobHandle(job_id=job_id, title=title)
        _JOBS[job_id] = handle
        _QUEUES[job_id] = handle.event_queue
    return handle


def get_handle(job_id: str) -> Optional[JobHandle]:
    return _JOBS.get(job_id)


def get_queue(job_id: str) -> Optional[asyncio.Queue]:
    return _QUEUES.get(job_id)


async def run_blocking(job_id: str, fn: Callable[..., Any], *args, **kwargs):
    """Run a blocking pipeline function in a worker thread while keeping
    the event sink bound to the current job_id."""
    handle = _JOBS.get(job_id) or register_job(job_id)
    handle.status = "running"

    loop = asyncio.get_running_loop()

    def _target():
        with with_event_sink(job_id, handle.event_queue):
            return fn(*args, **kwargs)

    try:
        result = await loop.run_in_executor(None, _target)
        handle.status = "done"
        handle.result = result if isinstance(result, dict) else None
        await handle.event_queue.put({
            "job_id": job_id, "phase": "pipeline", "event": "job_complete", "data": {}
        })
        return result
    except Exception as e:
        handle.status = "failed"
        handle.error = str(e)
        await handle.event_queue.put({
            "job_id": job_id, "phase": "pipeline", "event": "job_failed",
            "data": {"error": str(e)},
        })
        raise
