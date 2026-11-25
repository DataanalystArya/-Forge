"""Phase 6/7/8 — Debugging, Automation, Monitoring API tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.core.deps import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def client(engine):
    SessionLocal = sessionmaker(bind=engine)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(client: TestClient, email: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": "StrongPass1!", "full_name": "Test User"})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass1!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Phase 6 — Debugging API
# ---------------------------------------------------------------------------

class TestDebuggingAPI:
    def test_list_sessions_empty(self, client):
        h = _auth(client, "dbg_list@forge.dev")
        resp = client.get("/api/v1/debugging/sessions", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_start_session_missing_repo(self, client):
        h = _auth(client, "dbg_missing@forge.dev")
        resp = client.post(
            "/api/v1/debugging/sessions",
            json={"repo_id": "nonexistent-999", "title": "Test debug"},
            headers=h,
        )
        assert resp.status_code == 404

    def test_start_session_success(self, client):
        h = _auth(client, "dbg_start@forge.dev")
        r_repo = client.post("/api/v1/repositories", json={"full_name": "dbg/start-repo", "description": ""}, headers=h)
        repo_id = r_repo.json()["id"]

        with patch("app.api.debugging.start_agent_session"):
            resp = client.post(
                "/api/v1/debugging/sessions",
                json={"repo_id": repo_id, "title": "Phase 6 test session", "description": "Automated test"},
                headers=h,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["status"] == "PLANNING"

    def test_get_session_detail_and_diff(self, client):
        h = _auth(client, "dbg_detail@forge.dev")
        r_repo = client.post("/api/v1/repositories", json={"full_name": "dbg/detail-repo", "description": ""}, headers=h)
        repo_id = r_repo.json()["id"]

        with patch("app.api.debugging.start_agent_session"):
            r_sess = client.post(
                "/api/v1/debugging/sessions",
                json={"repo_id": repo_id, "title": "Detail test", "description": "Detail desc"},
                headers=h,
            )
            sess_id = r_sess.json()["session_id"]

        resp = client.get(f"/api/v1/debugging/sessions/{sess_id}", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert "agent_executions" in body
        assert "patches" in body
        assert "security_findings" in body
        assert "test_results" in body

        # Diff
        resp_diff = client.get(f"/api/v1/debugging/sessions/{sess_id}/diff", headers=h)
        assert resp_diff.status_code == 200
        assert "diff" in resp_diff.json()

    def test_cross_user_isolation(self, client):
        h1 = _auth(client, "dbg_u1@forge.dev")
        h2 = _auth(client, "dbg_u2@forge.dev")

        r_repo = client.post("/api/v1/repositories", json={"full_name": "dbg/iso-repo", "description": ""}, headers=h1)
        repo_id = r_repo.json()["id"]

        with patch("app.api.debugging.start_agent_session"):
            r_sess = client.post(
                "/api/v1/debugging/sessions",
                json={"repo_id": repo_id, "title": "Iso test", "description": "desc"},
                headers=h1,
            )
            sess_id = r_sess.json()["session_id"]

        r = client.get(f"/api/v1/debugging/sessions/{sess_id}", headers=h2)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Phase 7 — GitHub Automation API
# ---------------------------------------------------------------------------

class TestGitHubAutomationAPI:
    def test_list_prs_empty(self, client):
        h = _auth(client, "gh_prs@forge.dev")
        resp = client.get("/api/v1/automation/pull-requests", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_approve_patch_missing_session(self, client):
        h = _auth(client, "gh_appr@forge.dev")
        resp = client.post(
            "/api/v1/automation/sessions/nonexistent-id/approve",
            json={"patch_id": "nonexistent-patch"},
            headers=h,
        )
        assert resp.status_code == 404

    def test_session_diff_endpoint(self, client):
        h = _auth(client, "gh_diff@forge.dev")
        r_repo = client.post("/api/v1/repositories", json={"full_name": "gh/diff-repo", "description": ""}, headers=h)
        repo_id = r_repo.json()["id"]

        with patch("app.api.debugging.start_agent_session"):
            r_sess = client.post(
                "/api/v1/debugging/sessions",
                json={"repo_id": repo_id, "title": "Diff test", "description": "desc"},
                headers=h,
            )
            sess_id = r_sess.json()["session_id"]

        resp = client.get(f"/api/v1/automation/sessions/{sess_id}/diff", headers=h)
        assert resp.status_code == 200
        assert "patches" in resp.json()


# ---------------------------------------------------------------------------
# Phase 8 — Monitoring API
# ---------------------------------------------------------------------------

class TestMonitoringAPI:
    def test_overview_returns_correct_shape(self, client):
        h = _auth(client, "mon_ov@forge.dev")
        resp = client.get("/api/v1/monitoring/overview", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert "total_sessions" in body
        assert "success_rate_pct" in body
        assert "total_tokens_used" in body
        assert "estimated_cost_usd" in body

    def test_llm_usage_paginated(self, client):
        h = _auth(client, "mon_llm@forge.dev")
        resp = client.get("/api/v1/monitoring/llm-usage?page=1&per_page=10", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_session_metrics_list(self, client):
        h = _auth(client, "mon_metrics@forge.dev")
        resp = client.get("/api/v1/monitoring/sessions/metrics", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_evaluation_metrics_list(self, client):
        h = _auth(client, "mon_eval@forge.dev")
        resp = client.get("/api/v1/monitoring/evaluation-metrics", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
