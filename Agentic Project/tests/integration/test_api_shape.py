"""Integration rubric: backend routes register, shapes look right."""
from fastapi.testclient import TestClient

from backend.app import app


def test_healthz():
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_state_404_for_unknown_job():
    with TestClient(app) as c:
        r = c.get("/api/state/does_not_exist")
        assert r.status_code == 404


def test_versions_empty_for_unknown_job():
    with TestClient(app) as c:
        r = c.get("/api/versions/does_not_exist")
        assert r.status_code == 200
        assert r.json() == []
