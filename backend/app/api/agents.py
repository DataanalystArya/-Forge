"""
Agents & Multi-Agent Orchestration API Router — Phase 4.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.graph import start_agent_session
from app.core.deps import get_current_user, get_db
from app.models.repository import Repository
from app.models.session import (
    AgentExecution,
    DebuggingSession,
    Patch,
    PullRequest,
    SecurityFinding,
    TestExecution,
)
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.ws_manager import ws_manager

logger = logging.getLogger("forge.api.agents")
router = APIRouter(prefix="/agents", tags=["Agents"])

AGENT_CATALOG = [
    {"id": "planner", "name": "PlannerAgent", "order": 1, "role": "Task Decomposition & Workflow Sequencing"},
    {"id": "repo_analyst", "name": "RepositoryAnalysisAgent", "order": 2, "role": "Codebase Architecture, RAG & GraphRAG Context"},
    {"id": "bug_detector", "name": "BugDetectionAgent", "order": 3, "role": "AST Anomaly & Root Cause Investigation"},
    {"id": "security_auditor", "name": "SecurityAuditAgent", "order": 4, "role": "Static Security Vulnerability Audit"},
    {"id": "coding", "name": "CodingAgent", "order": 5, "role": "Patch & Unified Diff Generation"},
    {"id": "testing", "name": "TestingAgent", "order": 6, "role": "Isolated Pytest Suite Execution"},
    {"id": "code_review", "name": "CodeReviewAgent", "order": 7, "role": "Verification Gate & Regression Review"},
    {"id": "self_repair", "name": "SelfRepairAgent", "order": 8, "role": "Bounded Iterative Failure Repair Loop"},
]


class CreateSessionRequest(BaseModel):
    repository_id: str
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=2)
    error_logs: str = ""
    max_retries: int = Field(default=3, ge=0, le=5)


def _owned_repo(repo_id: str, user: User, db: Session) -> Repository:
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")
    if repo.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return repo


def _owned_session(session_id: str, user: User, db: Session) -> DebuggingSession:
    sess = db.query(DebuggingSession).filter(DebuggingSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")
    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return sess


@router.get("/specs")
def get_agent_specs(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "orchestrator": "LangGraph StateGraph (MemorySaver)",
        "llm_configured": LLMService.is_configured(),
        "llm_model": LLMService.get_model_name(),
        "agents": AGENT_CATALOG,
    }


@router.post("/sessions", status_code=status.HTTP_202_ACCEPTED)
def create_and_run_session(
    body: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    repo = _owned_repo(body.repository_id, current_user, db)

    sess = DebuggingSession(
        repository_id=repo.id,
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        error_logs=body.error_logs,
        status="PLANNING",
        current_phase="PlannerAgent",
        retry_count=0,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    start_agent_session(
        session_id=sess.id,
        repository_id=repo.id,
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        error_logs=body.error_logs,
        max_retries=body.max_retries,
    )

    return {
        "id": sess.id,
        "repository_id": sess.repository_id,
        "title": sess.title,
        "status": sess.status,
        "current_phase": sess.current_phase,
        "llm_configured": LLMService.is_configured(),
        "created_at": sess.created_at,
    }


@router.get("/sessions")
def list_sessions(
    repository_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(DebuggingSession).filter(DebuggingSession.user_id == current_user.id)
    if repository_id:
        q = q.filter(DebuggingSession.repository_id == repository_id)
    sessions = q.order_by(DebuggingSession.created_at.desc()).limit(50).all()
    return [
        {
            "id": s.id,
            "repository_id": s.repository_id,
            "title": s.title,
            "description": s.description,
            "status": s.status,
            "current_phase": s.current_phase,
            "retry_count": s.retry_count,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sess = _owned_session(session_id, current_user, db)

    executions = (
        db.query(AgentExecution)
        .filter(AgentExecution.session_id == session_id)
        .order_by(AgentExecution.created_at.asc())
        .all()
    )
    patches = (
        db.query(Patch)
        .filter(Patch.session_id == session_id)
        .order_by(Patch.iteration.asc())
        .all()
    )
    tests = (
        db.query(TestExecution)
        .filter(TestExecution.session_id == session_id)
        .order_by(TestExecution.created_at.asc())
        .all()
    )
    findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.session_id == session_id)
        .all()
    )
    prs = (
        db.query(PullRequest)
        .filter(PullRequest.session_id == session_id)
        .all()
    )

    return {
        "id": sess.id,
        "repository_id": sess.repository_id,
        "title": sess.title,
        "description": sess.description,
        "error_logs": sess.error_logs,
        "status": sess.status,
        "current_phase": sess.current_phase,
        "retry_count": sess.retry_count,
        "llm_configured": LLMService.is_configured(),
        "created_at": sess.created_at,
        "updated_at": sess.updated_at,
        "executions": [
            {
                "id": e.id,
                "agent_name": e.agent_name,
                "status": e.status,
                "duration_ms": e.duration_ms,
                "output": json.loads(e.output_state_json) if e.output_state_json else {},
                "error": e.error,
                "created_at": e.created_at,
            }
            for e in executions
        ],
        "patches": [
            {
                "id": p.id,
                "iteration": p.iteration,
                "diff_content": p.diff_content,
                "affected_files": json.loads(p.affected_files_json) if p.affected_files_json else [],
                "rationale": p.rationale,
                "is_applied": p.is_applied,
                "created_at": p.created_at,
            }
            for p in patches
        ],
        "test_executions": [
            {
                "id": t.id,
                "patch_id": t.patch_id,
                "exit_code": t.exit_code,
                "passed_count": t.passed_count,
                "failed_count": t.failed_count,
                "stdout": t.stdout,
                "stderr": t.stderr,
                "duration_ms": t.duration_ms,
                "created_at": t.created_at,
            }
            for t in tests
        ],
        "security_findings": [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "message": f.message,
                "recommendation": f.recommendation,
            }
            for f in findings
        ],
        "pull_requests": [
            {
                "id": pr.id,
                "branch_name": pr.branch_name,
                "pr_number": pr.pr_number,
                "pr_url": pr.pr_url,
                "title": pr.title,
                "status": pr.status,
            }
            for pr in prs
        ],
    }


@router.websocket("/ws/{session_id}")
async def agent_session_ws(websocket: WebSocket, session_id: str) -> None:
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)
