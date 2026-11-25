"""Phase 6 — Autonomous Debugging & Self-Repair API."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.agents.graph import start_agent_session
from app.models.user import User
from app.models.session import (
    DebuggingSession,
    AgentExecution,
    Patch,
    TestExecution,
    SecurityFinding,
)
from app.models.repository import Repository

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

    return {
        "id": s.id,
        "repo_id": s.repository_id,
        "status": s.status,
        "title": s.title,
        "description": s.description,
        "current_phase": s.current_phase,
        "retry_count": s.retry_count,
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
