"""Read-side helpers — paginated history and diff summaries for the UI."""
from __future__ import annotations

import json
from typing import List, Optional

from shared.schemas import VersionSnapshot

from .storage import VersionStorage


class HistoryIndex:
    def __init__(self, storage: Optional[VersionStorage] = None) -> None:
        self.storage = storage or VersionStorage()

    def list_for_job(self, job_id: str) -> List[dict]:
        """Return a UI-friendly history list for one job, with the active
        version flagged and each row carrying its parent_version pointer
        so the frontend can render the lineage on hover."""
        snaps = self.storage.list(job_id)
        active = self.storage.get_active(job_id)
        if active is None and snaps:
            # Legacy data: pick the highest-numbered version so the UI
            # has something to highlight.
            active = max(s.version for s in snaps)
        return [self._summarise(s, active=active) for s in snaps]

    def list_all_jobs(self) -> List[dict]:
        all_snaps = self.storage.list()
        by_job: dict[str, VersionSnapshot] = {}
        for s in all_snaps:
            if s.job_id not in by_job or by_job[s.job_id].version < s.version:
                by_job[s.job_id] = s
        return [
            {
                "job_id": s.job_id,
                "latest_version": s.version,
                "timestamp_ms": s.timestamp_ms,
                "title": _extract_title(s),
            }
            for s in sorted(by_job.values(), key=lambda x: -x.timestamp_ms)
        ]

    def _summarise(self, s: VersionSnapshot, active: Optional[int] = None) -> dict:
        return {
            "version": s.version,
            "parent_version": s.parent_version,
            "job_id": s.job_id,
            "timestamp_ms": s.timestamp_ms,
            "changed_phase": s.changed_phase,
            "change_summary": s.change_summary,
            "triggered_by": s.triggered_by,
            "title": _extract_title(s),
            "is_active": (active is not None and s.version == active),
        }


def _extract_title(s: VersionSnapshot) -> str:
    try:
        data = json.loads(s.state_json)
        return data.get("story", {}).get("title") or data.get("prompt", "")[:60]
    except Exception:
        return ""
