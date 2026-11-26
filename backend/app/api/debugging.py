"""Phase 6 — Autonomous Debugging & Self-Repair API."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.agents.graph import start_agent_session
from app.agents.nodes import _SECURITY_RULES, _iter_workspace_files
from app.models.observability import LLMUsageLog
from app.models.user import User
from app.models.session import (
    DebuggingSession,
    AgentExecution,
    Patch,
    TestExecution,
    SecurityFinding,
)
from app.models.repository import Repository
from app.services.llm_service import LLMService
from app.services.workspace_service import get_repo_workspace_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debugging", tags=["debugging"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StartDebuggingRequest(BaseModel):
    repo_id: str
    title: str = "Automated Debug Session"
    description: str = ""
    error_logs: str = ""
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session_for_user(session_id: str, db: Session, user: User) -> DebuggingSession:
    s = db.query(DebuggingSession).filter(DebuggingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Debugging session not found")
    if s.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return s


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/sessions")
def start_debugging_session(
    req: StartDebuggingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Launch an agent workflow session focused on debugging *repo_id*.
    Returns the session id; front-end polls /debugging/sessions/{id} for progress.
    """
    repo = db.query(Repository).filter(Repository.id == req.repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    session = DebuggingSession(
        repository_id=req.repo_id,
        user_id=current_user.id,
        title=req.title,
        description=req.description or f"Debug and audit repository: {repo.full_name}",
        error_logs=req.error_logs,
        status="PLANNING",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Fire-and-forget background agent execution
    start_agent_session(
        session_id=session.id,
        repository_id=req.repo_id,
        user_id=current_user.id,
        title=req.title,
        description=session.description,
        error_logs=req.error_logs,
        max_retries=req.max_retries,
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "title": session.title,
        "repo_id": req.repo_id,
    }


@router.get("/sessions")
def list_debugging_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all debugging sessions owned by current user."""
    sessions = (
        db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .order_by(DebuggingSession.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": s.id,
            "repo_id": s.repository_id,
            "status": s.status,
            "title": s.title,
            "current_phase": s.current_phase,
            "retry_count": s.retry_count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
def get_debugging_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return full session detail including agent executions, patches, test results."""
    s = _get_session_for_user(session_id, db, current_user)

    executions = (
        db.query(AgentExecution)
        .filter(AgentExecution.session_id == session_id)
        .order_by(AgentExecution.created_at)
        .all()
    )
    patches = (
        db.query(Patch)
        .filter(Patch.session_id == session_id)
        .order_by(Patch.created_at)
        .all()
    )
    findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.session_id == session_id)
        .all()
    )
    tests = (
        db.query(TestExecution)
        .filter(TestExecution.session_id == session_id)
        .order_by(TestExecution.created_at)
        .all()
    )
    live_llm_calls = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.session_id == session_id, LLMUsageLog.status == "SUCCESS")
        .count()
    )
    execution_mode = "LIVE_LLM" if live_llm_calls > 0 else "DETERMINISTIC_FALLBACK"

    return {
        "id": s.id,
        "repo_id": s.repository_id,
        "status": s.status,
        "title": s.title,
        "description": s.description,
        "current_phase": s.current_phase,
        "retry_count": s.retry_count,
        "llm_configured": LLMService.is_configured(),
        "execution_mode": execution_mode,
        "live_llm_calls": live_llm_calls,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "agent_executions": [
            {
                "agent": e.agent_name,
                "status": e.status,
                "duration_ms": e.duration_ms,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "output_summary": e.output_state_json,
                "error": e.error,
            }
            for e in executions
        ],
        "patches": [
            {
                "id": p.id,
                "iteration": p.iteration,
                "diff": p.diff_content,
                "rationale": p.rationale,
                "is_applied": p.is_applied,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in patches
        ],
        "security_findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "message": f.message,
                "recommendation": f.recommendation,
            }
            for f in findings
        ],
        "test_results": [
            {
                "id": t.id,
                "passed": t.passed_count,
                "failed": t.failed_count,
                "exit_code": t.exit_code,
                "stdout": t.stdout,
                "stderr": t.stderr,
                "duration_ms": t.duration_ms,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tests
        ],
    }


@router.get("/sessions/{session_id}/diff")
def get_latest_diff(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the latest patch diff for a session."""
    _get_session_for_user(session_id, db, current_user)
    patch = (
        db.query(Patch)
        .filter(Patch.session_id == session_id)
        .order_by(Patch.created_at.desc())
        .first()
    )
    if not patch:
        return {"diff": "", "rationale": "No patches generated", "is_applied": False}
    return {
        "patch_id": patch.id,
        "diff": patch.diff_content or "",
        "rationale": patch.rationale,
        "is_applied": patch.is_applied,
        "iteration": patch.iteration,
    }


# ---------------------------------------------------------------------------
# Security Audit Center Endpoints
# ---------------------------------------------------------------------------

class SecurityScanRequest(BaseModel):
    repo_id: str


@router.get("/security-findings")
def list_security_findings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return all recorded security findings across the current user's sessions."""
    sessions = (
        db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .all()
    )
    sess_map = {s.id: s for s in sessions}
    if not sess_map:
        return []
    repos = {
        r.id: r.full_name
        for r in db.query(Repository).filter(Repository.user_id == current_user.id).all()
    }
    findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.session_id.in_(list(sess_map.keys())))
        .order_by(SecurityFinding.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": f.id,
            "session_id": f.session_id,
            "repo_id": sess_map[f.session_id].repository_id if f.session_id in sess_map else "",
            "repo_name": repos.get(sess_map[f.session_id].repository_id, "Unknown") if f.session_id in sess_map else "Unknown",
            "rule_id": f.rule_id,
            "severity": f.severity,
            "file_path": f.file_path,
            "line_number": f.line_number,
            "message": f.message,
            "recommendation": f.recommendation,
        }
        for f in findings
    ]


@router.post("/security-scan")
def run_security_scan(
    req: SecurityScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run static AST & pattern security audit across a repository workspace."""
    repo = db.query(Repository).filter(Repository.id == req.repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    workspace_path = get_repo_workspace_path(repo.id)
    if not workspace_path.exists():
        raise HTTPException(status_code=400, detail="Repository workspace not cloned locally")

    session = DebuggingSession(
        repository_id=repo.id,
        user_id=current_user.id,
        title=f"Security Audit: {repo.full_name}",
        description="Standalone static & AST security audit scan",
        status="COMPLETED",
        current_phase="SecurityAuditAgent",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    findings_out: list[dict[str, Any]] = []
    files = _iter_workspace_files(str(workspace_path), max_files=250)
    for fp in files:
        if fp.suffix.lower() not in {".py", ".js", ".ts", ".jsx", ".tsx", ".yml", ".yaml"}:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fp.relative_to(workspace_path))
        for idx, line in enumerate(text.splitlines(), start=1):
            for rule_id, severity, pattern, message, rec in _SECURITY_RULES:
                if pattern.search(line):
                    sf = SecurityFinding(
                        repository_id=repo.id,
                        session_id=session.id,
                        rule_id=rule_id,
                        severity=severity,
                        file_path=rel,
                        line_number=idx,
                        message=message,
                        recommendation=rec,
                    )
                    db.add(sf)
                    findings_out.append({
                        "rule_id": rule_id,
                        "severity": severity,
                        "file_path": rel,
                        "line_number": idx,
                        "message": message,
                        "recommendation": rec,
                    })
                    if len(findings_out) >= 100:
                        break
            if len(findings_out) >= 100:
                break
        if len(findings_out) >= 100:
            break

    db.commit()
    return {
        "session_id": session.id,
        "repo_id": repo.id,
        "files_scanned": len(files),
        "findings_count": len(findings_out),
        "findings": findings_out,
    }


# ---------------------------------------------------------------------------
# Testing Center Endpoints
# ---------------------------------------------------------------------------

class RunTestsRequest(BaseModel):
    repo_id: str
    test_path: str = ""


@router.get("/test-runs")
def list_test_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all sandboxed test execution runs owned by the current user."""
    sessions = (
        db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .all()
    )
    sess_map = {s.id: s for s in sessions}
    if not sess_map:
        return []
    repos = {
        r.id: r.full_name
        for r in db.query(Repository).filter(Repository.user_id == current_user.id).all()
    }
    runs = (
        db.query(TestExecution)
        .filter(TestExecution.session_id.in_(list(sess_map.keys())))
        .order_by(TestExecution.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": t.id,
            "session_id": t.session_id,
            "session_title": sess_map[t.session_id].title if t.session_id in sess_map else "",
            "repo_id": sess_map[t.session_id].repository_id if t.session_id in sess_map else "",
            "repo_name": repos.get(sess_map[t.session_id].repository_id, "Unknown") if t.session_id in sess_map else "Unknown",
            "command": t.command,
            "passed": t.passed_count,
            "failed": t.failed_count,
            "exit_code": t.exit_code,
            "stdout": t.stdout,
            "stderr": t.stderr,
            "duration_ms": t.duration_ms,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in runs
    ]


@router.post("/run-tests")
def run_repository_tests(
    req: RunTestsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute pytest inside an isolated subprocess against a repository workspace."""
    import os
    import re
    import subprocess
    import sys
    import time

    repo = db.query(Repository).filter(Repository.id == req.repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    workspace_path = get_repo_workspace_path(repo.id)
    if not workspace_path.exists():
        raise HTTPException(status_code=400, detail="Repository workspace not cloned locally")

    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
    if req.test_path.strip():
        # Prevent path traversal or shell injection
        safe_target = req.test_path.strip().lstrip("/")
        if ".." in safe_target:
            raise HTTPException(status_code=400, detail="Invalid test path")
        cmd.append(safe_target)

    session = DebuggingSession(
        repository_id=repo.id,
        user_id=current_user.id,
        title=f"Sandbox Test Run: {repo.full_name}",
        description=f"Command: {' '.join(cmd)}",
        status="RUNNING",
        current_phase="TestingAgent",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{workspace_path}{os.pathsep}{workspace_path / 'src'}"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        stdout = proc.stdout[-8000:] if proc.stdout else ""
        stderr = proc.stderr[-4000:] if proc.stderr else ""
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        duration_ms = 60000
        stdout = ""
        stderr = "Test execution timed out after 60 seconds."
        exit_code = 124
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        stdout = ""
        stderr = str(exc)
        exit_code = 1

    m_pass = re.search(r"(\d+)\s+passed", stdout)
    m_fail = re.search(r"(\d+)\s+failed", stdout)
    if exit_code == 5:
        # Pytest exit code 5: no tests collected (not a test failure)
        passed_count = 0
        failed_count = 0
        if not stderr:
            stderr = "Pytest collected 0 tests (exit code 5). Ensure test files are named test_*.py or *_test.py."
    else:
        passed_count = int(m_pass.group(1)) if m_pass else (1 if exit_code == 0 else 0)
        failed_count = int(m_fail.group(1)) if m_fail else (0 if exit_code == 0 else 1)

    te = TestExecution(
        session_id=session.id,
        command=" ".join(cmd),
        exit_code=exit_code,
        passed_count=passed_count,
        failed_count=failed_count,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
    )
    db.add(te)
    session.status = "COMPLETED" if exit_code in (0, 5) else "FAILED"
    db.commit()
    db.refresh(te)

    return {
        "id": te.id,
        "session_id": session.id,
        "repo_id": repo.id,
        "command": te.command,
        "exit_code": exit_code,
        "passed": passed_count,
        "failed": failed_count,
        "duration_ms": duration_ms,
        "stdout": stdout,
        "stderr": stderr,
    }
