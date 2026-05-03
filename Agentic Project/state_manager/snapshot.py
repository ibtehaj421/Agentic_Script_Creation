"""Freeze asset files under `data/state_versions/<job>/v<N>/` so older
versions keep their assets even if the working output tree is rewritten.

We unconditionally **copy** (not hardlink) because hardlinks on POSIX
retain the same inode; an in-place truncating write (`open("wb")`) to the
working file would then corrupt every older snapshot that points at it.
On APFS the copy uses reflinks automatically so it's still near-free.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, List

from config import OUTPUTS_DIR, STATE_VERSIONS_DIR


class SnapshotStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base = Path(base_dir or STATE_VERSIONS_DIR)
        self.base.mkdir(parents=True, exist_ok=True)

    def dir_for(self, job_id: str, version: int) -> Path:
        return self.base / job_id / f"v{version:04d}"

    def freeze(self, job_id: str, version: int, asset_paths: Iterable[str]) -> Path:
        """Freeze the given files into the version's directory.

        Preserves the relative path from `data/outputs/` when possible so
        `restore()` can map them back.
        """
        out_dir = self.dir_for(job_id, version)
        out_dir.mkdir(parents=True, exist_ok=True)
        for raw in asset_paths:
            if not raw:
                continue
            src = Path(raw)
            if not src.exists() or src.is_dir():
                continue
            rel = _relative_to_outputs(src)
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                continue
            shutil.copy2(src, dst)
        return out_dir

    def restore(self, job_id: str, version: int) -> List[str]:
        """Copy frozen assets back under `data/outputs/`. Returns restored paths."""
        src_dir = self.dir_for(job_id, version)
        restored: List[str] = []
        if not src_dir.exists():
            return restored
        for file in src_dir.rglob("*"):
            if file.is_dir():
                continue
            rel = file.relative_to(src_dir)
            dst = OUTPUTS_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                if dst.exists() and dst.samefile(file):
                    dst.unlink()
            except OSError:
                pass
            shutil.copy2(file, dst)
            restored.append(str(dst))
        return restored


def _relative_to_outputs(p: Path) -> Path:
    try:
        return p.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return Path("_external") / p.name
