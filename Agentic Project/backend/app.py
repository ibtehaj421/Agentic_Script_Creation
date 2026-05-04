"""FastAPI entry point.

Mount:
    /api/*   — REST endpoints (generate, edit, undo, history, phase rerun)
    /ws/*    — WebSocket streams (per-job progress events)
    /media/* — Static file server for generated assets (final MP4, audio, etc.)

Run:   python -m uvicorn backend.app:app --reload --port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import OUTPUTS_DIR, ROOT

from .routes import edit_routes, generate_routes, media_routes, version_routes
from .websocket.progress_ws import router as ws_router

# Trigger MCP tool self-registration (idempotent).
import mcp.tools  # noqa: F401

FRONTEND_DIR = ROOT / "frontend"


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Video Generation API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # local dev — tighten if deploying
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(generate_routes.router, prefix="/api", tags=["pipeline"])
    app.include_router(edit_routes.router, prefix="/api", tags=["edit"])
    app.include_router(version_routes.router, prefix="/api", tags=["versions"])
    app.include_router(media_routes.router, prefix="/api", tags=["media"])
    app.include_router(ws_router, prefix="/ws", tags=["ws"])

    # Serve generated assets at /media/*
    app.mount("/media", StaticFiles(directory=str(OUTPUTS_DIR)), name="media")

    # Serve the frontend bundle at /static/* and the SPA entry at /
    static_dir = FRONTEND_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def spa_root():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"hint": "frontend not built; run `npm run build` in frontend/"}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
