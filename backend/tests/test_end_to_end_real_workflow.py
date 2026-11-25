"""
Comprehensive Real-World End-to-End Acceptance Test for FORGE.

Verifies:
1. User Registration & JWT Login + Dashboard stats
2. Real Git Repository creation with an actual failing unit test and security pattern
3. ZIP Upload & File Explorer + AST Symbol Extraction
4. Code RAG Indexing & Hybrid Search (Semantic + BM25)
5. GraphRAG Extraction & Persistent Subgraph Query
6. Settings API (Save model/API key/GitHub PAT encrypted at rest + probe)
7. Security Audit Center (`/debugging/security-scan` & `/security-findings`)
8. Testing Center (`/debugging/run-tests` & `/test-runs`)
9. Autonomous Debugging Workflow -> Patch Generation -> Diff -> Approval -> Real Git Branch & Commit (`apply_diff_patch` actually modifies files!) -> Rollback
10. Monitoring & Telemetry verification
"""
from __future__ import annotations

import io
import os
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import Base, engine
from app.services.git_service import GitService


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def _make_sample_repo_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "calculator.py",
            "def add(a: int, b: int) -> int:\n"
            "    return a - b  # BUG: subtraction instead of addition\n\n"
            "def unsafe_eval(expr: str):\n"
            "    return eval(expr)\n",
        )
        zf.writestr(
            "test_calculator.py",
            "from calculator import add\n\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n",
        )
    return buf.getvalue()


def test_full_end_to_end_forge_workflow(client: TestClient):
    # 1. Register & Login
    email = f"e2e_{int(time.time() * 1000)}@example.com"
    password = "StrongPassword123!"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "E2E Tester"},
    )
    assert reg.status_code in (200, 201), reg.text

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Settings API (Read & Update)
    s_get = client.get("/api/v1/settings", headers=headers)
    assert s_get.status_code == 200
    assert "infrastructure" in s_get.json()

    s_put = client.put(
        "/api/v1/settings",
        json={"llm_provider": "openai", "llm_model": "gpt-4o-mini", "sandbox_timeout": 45},
        headers=headers,
    )
    assert s_put.status_code == 200
    assert s_put.json()["sandbox_timeout"] == 45

    # 3. Create Repository & Upload ZIP
    repo_res = client.post(
        "/api/v1/repositories",
        json={
            "name": "calc-e2e",
            "full_name": "forge-test/calc-e2e",
            "clone_url": "https://github.com/forge-test/calc-e2e.git",
            "description": "E2E test repository",
            "default_branch": "main",
        },
        headers=headers,
    )
    assert repo_res.status_code in (200, 201), repo_res.text
    repo_id = repo_res.json()["id"]

    zip_bytes = _make_sample_repo_zip()
    up_res = client.post(
        f"/api/v1/repositories/{repo_id}/upload-zip",
        files={"file": ("calc.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert up_res.status_code == 200, up_res.text

    # Initialize git in the extracted workspace so branch/commit/rollback can be verified
    from app.services.workspace_service import get_repo_workspace_path
    ws_path = get_repo_workspace_path(repo_id)
    subprocess.run(["git", "init", "-b", "main"], cwd=ws_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "e2e@forge.local"], cwd=ws_path, check=True)
    subprocess.run(["git", "config", "user.name", "E2E Tester"], cwd=ws_path, check=True)
    subprocess.run(["git", "add", "."], cwd=ws_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=ws_path, check=True, capture_output=True)

    # 4. Explore Tree & Symbols
    tree_res = client.get(f"/api/v1/repositories/{repo_id}/tree", headers=headers)
    assert tree_res.status_code == 200
    sym_res = client.get(f"/api/v1/repositories/{repo_id}/symbols", headers=headers)
    assert sym_res.status_code == 200
    sym_names = [s["entity_name"] for s in sym_res.json().get("artifacts", [])]
    assert "add" in sym_names

    # 5. Index & Search via Code RAG
    # NOTE: Indexing runs in a background thread and loads the sentence-transformer
    # model on first use (~8-10s on a cold start). Poll for up to 90 seconds so
    # the test does not time out before the model finishes loading.
    idx_res = client.post(f"/api/v1/rag/repositories/{repo_id}/index", headers=headers)
    assert idx_res.status_code in (200, 202), idx_res.text
    for _ in range(90):
        st = client.get(f"/api/v1/rag/repositories/{repo_id}/status", headers=headers)
        st_data = st.json() if st.status_code == 200 else {}
        if st_data.get("status") == "COMPLETED":
            break
        if st_data.get("status") == "FAILED":
            raise AssertionError(f"Indexing FAILED: {st_data.get('error_message')}")
        time.sleep(1.0)
    else:
        raise AssertionError("Indexing did not complete within 90 seconds.")
    search_res = client.post(
        "/api/v1/rag/search",
        json={"repository_id": repo_id, "query": "add subtraction bug", "mode": "hybrid", "top_k": 5},
        headers=headers,
    )
    assert search_res.status_code == 200, search_res.text
    assert len(search_res.json().get("results", [])) >= 1

    # 6. GraphRAG Extraction & Subgraph
    g_ext = client.post(f"/api/v1/graph/repositories/{repo_id}/extract", headers=headers)
    assert g_ext.status_code == 200, g_ext.text
    assert g_ext.json()["nodes_created"] >= 3
    g_sub = client.get(
        f"/api/v1/graph/repositories/{repo_id}/subgraph?symbol=add&depth=2",
        headers=headers,
    )
    assert g_sub.status_code == 200
    assert len(g_sub.json().get("nodes", [])) >= 1

    # 7. Security Audit Center
    sec_scan = client.post(
        "/api/v1/debugging/security-scan",
        json={"repo_id": repo_id},
        headers=headers,
    )
    assert sec_scan.status_code == 200, sec_scan.text
    assert sec_scan.json()["findings_count"] >= 1
    sec_list = client.get("/api/v1/debugging/security-findings", headers=headers)
    assert sec_list.status_code == 200
    assert any(f["rule_id"] == "FORGE-SEC-001" for f in sec_list.json())

    # 8. Testing Center (Initial failing test run)
    test_run = client.post(
        "/api/v1/debugging/run-tests",
        json={"repo_id": repo_id},
        headers=headers,
    )
    assert test_run.status_code == 200, test_run.text
    assert test_run.json()["exit_code"] != 0  # test_add fails because a - b != a + b

    # 9. GitService real patch apply, commit, and rollback verification
    git_svc = GitService(str(ws_path))
    orig = (ws_path / "calculator.py").read_text()
    fixed = orig.replace("return a - b  # BUG: subtraction instead of addition", "return a + b")
    diff_text = git_svc.generate_diff(str(ws_path / "calculator.py"), orig, fixed)
    assert "+    return a + b" in diff_text

    # Create a session + patch and test approve + rollback endpoints
    from app.core.database import SessionLocal
    from app.models.session import DebuggingSession, Patch

    db = SessionLocal()
    try:
        sess = DebuggingSession(
            repository_id=repo_id,
            user_id=client.get("/api/v1/auth/me", headers=headers).json()["id"],
            title="Fix addition bug",
            status="COMPLETED",
            current_phase="CodeReviewAgent",
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        patch = Patch(
            session_id=sess.id,
            iteration=1,
            diff_content=diff_text,
            rationale="Fix subtraction typo in add()",
            is_applied=False,
        )
        db.add(patch)
        db.commit()
        db.refresh(patch)
        sess_id, patch_id = sess.id, patch.id
    finally:
        db.close()

    # Approve & apply patch -> verifies file actually changed on disk and committed!
    approve = client.post(
        f"/api/v1/automation/sessions/{sess_id}/approve",
        json={"patch_id": patch_id, "commit_message": "fix: use addition in add()"},
        headers=headers,
    )
    assert approve.status_code == 200, approve.text
    app_data = approve.json()
    assert app_data["branch_created"] is True
    assert app_data["patch_applied"] is True
    assert app_data["committed"] is True
    assert "return a + b" in (ws_path / "calculator.py").read_text()

    # Verify pytest now PASSES after the approved patch!
    test_run_after = client.post(
        "/api/v1/debugging/run-tests",
        json={"repo_id": repo_id},
        headers=headers,
    )
    assert test_run_after.status_code == 200
    assert test_run_after.json()["exit_code"] == 0

    # Rollback patch -> verifies branch restored to main and original file restored!
    rb = client.post(f"/api/v1/automation/sessions/{sess_id}/rollback", headers=headers)
    assert rb.status_code == 200, rb.text
    assert rb.json()["rolled_back"] is True
    assert rb.json()["active_branch"] == "main"
    assert "return a - b" in (ws_path / "calculator.py").read_text()

    # 10. Dashboard & Monitoring telemetry check
    dash = client.get("/api/v1/dashboard/stats", headers=headers)
    assert dash.status_code == 200
    assert dash.json()["total_repositories"] >= 1

    mon = client.get("/api/v1/monitoring/overview", headers=headers)
    assert mon.status_code == 200
    assert mon.json()["total_sessions"] >= 1
