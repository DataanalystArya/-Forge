"""Phase 5 — GraphRAG tests."""
from __future__ import annotations

import os
import tempfile
import textwrap
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.core.deps import get_db
from app.main import app
from app.services.graph_service import GraphService, _extract_py_graph, _extract_js_ts_graph


# ---------------------------------------------------------------------------
# Fixtures
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
    client.post("/api/v1/auth/register", json={"email": email, "password": "StrongPass1!", "full_name": "Graph Tester"})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass1!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Unit tests — AST extractor
# ---------------------------------------------------------------------------

def test_extract_py_graph_basic():
    """Python AST extractor produces class/function nodes and edges."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(textwrap.dedent("""
            import os
            from pathlib import Path

            class MyClass(object):
                def method_a(self):
                    pass

            def standalone():
                MyClass()
        """))
        fname = f.name

    try:
        nodes, edges = _extract_py_graph(fname, "repo1")
        labels = [n["label"] for n in nodes]
        assert "Class" in labels
        assert "Function" in labels
        relations = [e["relation"] for e in edges]
        assert "IMPORTS" in relations
        assert "CONTAINS" in relations
    finally:
        os.unlink(fname)


def test_extract_js_ts_graph_basic():
    """JS/TS regex extractor captures function and class declarations."""
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write(textwrap.dedent("""
            import { foo } from './foo';
            export class ApiClient {
              async fetchData() {}
            }
            export function helper(x: number): string { return ''; }
        """))
        fname = f.name

    try:
        nodes, edges = _extract_js_ts_graph(fname)
        names = [n["name"] for n in nodes]
        assert "ApiClient" in names or "helper" in names
        relations = [e["relation"] for e in edges]
        assert "IMPORTS" in relations or "CONTAINS" in relations
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# GraphService unit tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_graph_service():
    """Ensure a fresh GraphService singleton for each test."""
    GraphService.reset()
    yield
    GraphService.reset()


def test_graph_service_uses_networkx_fallback():
    svc = GraphService.get_instance()
    assert not svc.neo4j_connected


def test_extract_and_summary():
    """extract_code_graph + get_graph_summary on a temp Python project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "mod.py"), "w") as f:
            f.write("class A:\n    def run(self): pass\n")
        with open(os.path.join(tmpdir, "util.py"), "w") as f:
            f.write("import os\ndef helper(): pass\n")

        svc = GraphService.get_instance()
        result = svc.extract_code_graph("repo_test", tmpdir)
        assert result["nodes"] > 0
        assert result["files_scanned"] == 2

        summary = svc.get_graph_summary("repo_test")
        assert summary["available"] is True
        assert summary["nodes"] > 0


def test_query_subgraph_finds_symbol():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "app.py"), "w") as f:
            f.write("class AuthService:\n    def login(self): pass\n")
        svc = GraphService.get_instance()
        svc.extract_code_graph("repo_q", tmpdir)
        result = svc.query_subgraph("repo_q", "AuthService", depth=2)
        assert result["available"] is True
        node_labels = [n["data"]["label"] for n in result["nodes"]]
        assert any("AuthService" in lbl or "auth" in lbl.lower() for lbl in node_labels)


def test_query_context_returns_matches():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "db.py"), "w") as f:
            f.write("class DatabaseManager:\n    pass\n")
        svc = GraphService.get_instance()
        svc.extract_code_graph("repo_ctx", tmpdir)
        ctx = svc.query_context("repo_ctx", "Database", limit=5)
        assert ctx["available"] is True
        assert len(ctx["nodes"]) >= 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_graph_subgraph_requires_symbol(client):
    h = _auth(client, "graph_sub@forge.dev")
    r_repo = client.post("/api/v1/repositories", json={"full_name": "graph/sub-test", "description": ""}, headers=h)
    repo_id = r_repo.json()["id"]

    resp = client.get(f"/api/v1/graph/repositories/{repo_id}/subgraph", headers=h)
    assert resp.status_code == 400


def test_graph_summary_endpoint(client):
    h = _auth(client, "graph_sum@forge.dev")
    r_repo = client.post("/api/v1/repositories", json={"full_name": "graph/sum-test", "description": ""}, headers=h)
    repo_id = r_repo.json()["id"]

    resp = client.get(f"/api/v1/graph/repositories/{repo_id}/summary", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body


def test_graph_cross_user_isolation(client):
    h1 = _auth(client, "graph_u1@forge.dev")
    h2 = _auth(client, "graph_u2@forge.dev")

    r_repo = client.post("/api/v1/repositories", json={"full_name": "graph/iso-test", "description": ""}, headers=h1)
    repo_id = r_repo.json()["id"]

    r = client.get(f"/api/v1/graph/repositories/{repo_id}/summary", headers=h2)
    assert r.status_code == 403
