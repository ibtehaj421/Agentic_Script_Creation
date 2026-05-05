"""/ws/progress/{job_id}

Relays the job's event queue into a WebSocket. Frontend hooks onto this
to paint per-phase progress and show thumbnails as they're produced.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.job_runner import get_queue, register_job

router = APIRouter()


@router.websocket("/progress/{job_id}")
async def progress(ws: WebSocket, job_id: str):
    await ws.accept()
    # Ensure a queue exists even if the client connects before the job starts
    queue = get_queue(job_id) or register_job(job_id).event_queue
    try:
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                # Heartbeat keeps intermediate proxies happy
                await ws.send_text(json.dumps({"event": "heartbeat"}))
                continue
            await ws.send_text(json.dumps(evt))
            if evt.get("event") in ("job_complete", "job_failed"):
                break
    except WebSocketDisconnect:
        return
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass
