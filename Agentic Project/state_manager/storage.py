"""SQLite-backed append-only log of version snapshots.

Schema:
    versions(
      id          INTEGER PRIMARY KEY,
      job_id      TEXT NOT NULL,
      version     INTEGER NOT NULL,
      parent_version INTEGER,           -- which version this one was made FROM
      timestamp_ms INTEGER NOT NULL,
      state_json  TEXT NOT NULL,
      asset_dir   TEXT NOT NULL,
      changed_phase TEXT NOT NULL DEFAULT '',
      change_summary TEXT NOT NULL DEFAULT '',
      triggered_by TEXT NOT NULL DEFAULT 'pipeline',
      UNIQUE(job_id, version)
    )
    active_version(
      job_id  TEXT PRIMARY KEY,
      version INTEGER NOT NULL          -- the currently checked-out version
    )

Every edit appends a new row — we never UPDATE or DELETE existing rows,
which satisfies the spec's "append-only log … no version is ever
permanently lost" guarantee. Undo / restore moves the `active_version`
pointer to a prior version — it does NOT insert a new row. New edits made
while the pointer is on vN create vN+1 with parent_version = N, which
gives us git-style branching (the active version's lineage is the chain
of parent_versions back to the root v1).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from config import STATE_DB
from shared.schemas import VersionSnapshot


DDL = """
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  parent_version INTEGER,
  timestamp_ms INTEGER NOT NULL,
  state_json TEXT NOT NULL,
  asset_dir TEXT NOT NULL,
  changed_phase TEXT NOT NULL DEFAULT '',
  change_summary TEXT NOT NULL DEFAULT '',
  triggered_by TEXT NOT NULL DEFAULT 'pipeline',
  UNIQUE(job_id, version)
);
CREATE INDEX IF NOT EXISTS idx_versions_job ON versions(job_id, version);

CREATE TABLE IF NOT EXISTS active_version (
  job_id  TEXT PRIMARY KEY,
  version INTEGER NOT NULL
);
"""


class VersionStorage:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or STATE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        # Use immediate transactions for write-safety across worker threads.
        conn = sqlite3.connect(self.db_path, isolation_level="IMMEDIATE", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript(DDL)
            # Idempotent migration for DBs created before parent_version
            # existed. SQLite errors if the column already exists, which we
            # swallow.
            try:
                c.execute("ALTER TABLE versions ADD COLUMN parent_version INTEGER")
            except sqlite3.OperationalError:
                pass

    def next_version(self, job_id: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM versions WHERE job_id=?",
                (job_id,),
            ).fetchone()
            return int(row["v"]) + 1

    def insert(self, snap: VersionSnapshot) -> int:
        parent = getattr(snap, "parent_version", None)
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO versions
                     (job_id, version, parent_version, timestamp_ms, state_json,
                      asset_dir, changed_phase, change_summary, triggered_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snap.job_id, snap.version, parent, snap.timestamp_ms,
                    snap.state_json, snap.asset_dir,
                    snap.changed_phase, snap.change_summary, snap.triggered_by,
                ),
            )
            return int(cur.lastrowid)

    # ── Active-version pointer ──────────────────────────────────────────
    def get_active(self, job_id: str) -> Optional[int]:
        with self._conn() as c:
            row = c.execute(
                "SELECT version FROM active_version WHERE job_id=?",
                (job_id,),
            ).fetchone()
        return int(row["version"]) if row else None

    def set_active(self, job_id: str, version: int) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO active_version (job_id, version) VALUES (?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET version = excluded.version""",
                (job_id, version),
            )

    def get(self, job_id: str, version: int) -> Optional[VersionSnapshot]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM versions WHERE job_id=? AND version=?",
                (job_id, version),
            ).fetchone()
        return _row_to_snap(row) if row else None

    def latest(self, job_id: str) -> Optional[VersionSnapshot]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM versions WHERE job_id=? ORDER BY version DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        return _row_to_snap(row) if row else None

    def list(self, job_id: Optional[str] = None) -> List[VersionSnapshot]:
        q = "SELECT * FROM versions"
        args: tuple = ()
        if job_id:
            q += " WHERE job_id=?"
            args = (job_id,)
        q += " ORDER BY version ASC"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [_row_to_snap(r) for r in rows]


def _row_to_snap(row: sqlite3.Row) -> VersionSnapshot:
    parent = row["parent_version"] if "parent_version" in row.keys() else None
    return VersionSnapshot(
        version=row["version"],
        parent_version=parent,
        job_id=row["job_id"],
        timestamp_ms=row["timestamp_ms"],
        state_json=row["state_json"],
        asset_dir=row["asset_dir"],
        changed_phase=row["changed_phase"],
        change_summary=row["change_summary"],
        triggered_by=row["triggered_by"],
    )
