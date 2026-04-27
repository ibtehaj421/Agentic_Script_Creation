"""Small IO helpers — safe filenames, atomic writes, timestamps, hashes."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from pathlib import Path


def ensure_dir(p: str | os.PathLike) -> Path:
    out = Path(p)
    out.mkdir(parents=True, exist_ok=True)
    return out


def job_dir(base: str | os.PathLike, job_id: str | None) -> Path:
    """Return a job-scoped subdirectory of `base`, created on demand.

    Every tool that writes outputs should resolve its output dir via this
    helper so two jobs can never overwrite each other's files. Falls back
    to `base` itself when `job_id` is missing (unit tests, ad-hoc tool
    runs) so existing call sites keep working.
    """
    out = Path(base) / job_id if job_id else Path(base)
    out.mkdir(parents=True, exist_ok=True)
    return out


def hash_short(s: str, n: int = 10) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:n]


def safe_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return slug or "unnamed"


def timestamp_ms() -> int:
    return int(time.time() * 1000)


def atomic_write_bytes(path: str | os.PathLike, data: bytes) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, delete=False, suffix=path.suffix
    ) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def atomic_write_text(path: str | os.PathLike, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def persist_state_manifest(state) -> Path:
    """Write the canonical `<job_id>_state.json` manifest for `state`.

    Called at the end of every phase so the on-disk manifest is always in
    sync with the in-memory state. Without this, partial re-renders that
    bypass `scripts/run_pipeline.py` (or that bump cache keys mid-flight)
    leave the manifest pointing at stale asset paths, which the next load
    would then surface as wrong-voice / wrong-portrait bugs.
    """
    # Deferred import to avoid circular dep (config → utils → schemas → utils).
    from config import OUTPUTS_DIR

    out = Path(OUTPUTS_DIR) / f"{state.job_id}_state.json"
    atomic_write_text(out, state.model_dump_json(indent=2))
    return out
