"""
Phase 4 — Multi-Agent LangGraph Orchestration Tests.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
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

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(client: TestClient, email: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": "StrongPass1!", "full_name": "Agent Tester"})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass1!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_agent_specs_endpoint(client):
    headers = _auth(client, "agents_specs@forge.dev")
    r = client.get("/api/v1/agents/specs", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["agents"]) == 8
    assert "LangGraph" in data["orchestrator"]


def test_langgraph_workflow_runs_real_static_and_pytest(engine):
    """Run the compiled LangGraph workflow on a real temp repo with a real bug & passing/failing test."""
    from app.agents.graph import run_session_sync
    from app.core import database as core_db

    SessionLocal = sessionmaker(bind=engine)
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "calc.py").write_text(
            "def bad_fn(items=[]):\n"
            "    try:\n"
            "        return eval('1 + 1')\n"
            "    except:\n"
            "        return 0\n"
        )
        (ws / "test_calc.py").write_text(
            "from calc import bad_fn\n"
            "def test_bad_fn():\n"
            "    assert bad_fn() == 2\n"
        )

        with patch.object(core_db, "SessionLocal", SessionLocal):
            final = run_session_sync({
                "session_id": "test-langgraph-session-1",
                "repository_id": "repo-1",
                "user_id": "user-1",
                "workspace_dir": str(ws),
                "issue_title": "Audit calc.py",
                "issue_description": "Find AST bugs and security issues",
                "error_logs": 'File "calc.py", line 3',
                "max_retries": 2,
                "retry_count": 0,
                "agent_events": [],
                "errors": [],
            })

    assert final["status"] == "COMPLETED"
    agents_ran = [e["agent"] for e in final["agent_events"]]
    assert "PlannerAgent" in agents_ran
    assert "RepositoryAnalysisAgent" in agents_ran
    assert "BugDetectionAgent" in agents_ran
    assert "SecurityAuditAgent" in agents_ran
    assert "CodingAgent" in agents_ran
    assert "TestingAgent" in agents_ran
    assert "CodeReviewAgent" in agents_ran

    # Bug detector found MutableDefaultArg + BareExcept + StackTraceReference
    categories = {b["category"] for b in final["bug_reports"]}
    assert "MutableDefaultArg" in categories
    assert "BareExcept" in categories
    # Security auditor found eval()
    rules = {f["rule_id"] for f in final["security_findings"]}
    assert "FORGE-SEC-001" in rules
    # TestingAgent ran real pytest and observed 1 passed
    assert final["test_result"]["tests_found"] is True
    assert final["test_result"]["passed_count"] == 1


def test_agent_session_cross_user_isolation(client):
    h1 = _auth(client, "agent_u1@forge.dev")
    h2 = _auth(client, "agent_u2@forge.dev")

    r_repo = client.post("/api/v1/repositories", json={"full_name": "u1/agent-repo", "description": ""}, headers=h1)
    repo_id = r_repo.json()["id"]

    with patch("app.api.agents.start_agent_session"):
        r_sess = client.post(
            "/api/v1/agents/sessions",
            json={"repository_id": repo_id, "title": "Check", "description": "Check bug"},
            headers=h1,
        )
        assert r_sess.status_code == 202
        sess_id = r_sess.json()["id"]

    r_forbidden = client.get(f"/api/v1/agents/sessions/{sess_id}", headers=h2)
    assert r_forbidden.status_code == 403
