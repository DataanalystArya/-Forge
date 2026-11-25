"""Phase 8 — Monitoring & Evaluation API endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.session import DebuggingSession, AgentExecution, TestExecution
from app.models.observability import LLMUsageLog, EvaluationMetric
from app.models.repository import Repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overview")
def monitoring_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    High-level dashboard metrics for the current user.
    """
    # Sessions owned by this user
    sessions = (
        db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .all()
    )
    total = len(sessions)
    completed = sum(1 for s in sessions if s.status == "COMPLETED")
    failed = sum(1 for s in sessions if s.status == "FAILED")
    success_rate = round((completed / total * 100) if total else 0, 1)

    # Test results
    session_ids = [s.id for s in sessions]
    tests = (
        db.query(TestExecution)
        .filter(TestExecution.session_id.in_(session_ids))
        .all()
    )
    total_passed = sum(t.passed_count or 0 for t in tests)
    total_failed_tests = sum(t.failed_count or 0 for t in tests)

    # LLM usage
    usage_logs = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.session_id.in_(session_ids))
        .all()
    )
    total_tokens = sum(u.total_tokens or 0 for u in usage_logs)
    estimated_cost = sum(u.estimated_cost_usd or 0.0 for u in usage_logs)

    # Avg duration
    durations = []
    for s in sessions:
        if s.created_at and s.updated_at and s.status in ("COMPLETED", "FAILED"):
            durations.append((s.updated_at - s.created_at).total_seconds())
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "failed_sessions": failed,
        "running_sessions": total - completed - failed,
        "success_rate_pct": success_rate,
        "total_tokens_used": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 4),
        "avg_session_duration_seconds": avg_duration,
        "total_tests_passed": total_passed,
        "total_tests_failed": total_failed_tests,
        "llm_calls": len(usage_logs),
    }


@router.get("/llm-usage")
def llm_usage(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Paginated LLM usage log for the current user's sessions."""
    session_ids = [
        s.id
        for s in db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .all()
    ]
    total = db.query(LLMUsageLog).filter(LLMUsageLog.session_id.in_(session_ids)).count()
    logs = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.session_id.in_(session_ids))
        .order_by(LLMUsageLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": u.id,
                "model": u.model_name,
                "agent": u.agent_name,
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.total_tokens,
                "estimated_cost_usd": u.estimated_cost_usd,
                "latency_ms": u.latency_ms,
                "status": u.status,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in logs
        ],
    }


@router.get("/sessions/metrics")
def session_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Per-session agent timing breakdown for recharts consumption."""
    sessions = (
        db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .order_by(DebuggingSession.created_at.desc())
        .limit(20)
        .all()
    )

    result = []
    for s in sessions:
        execs = db.query(AgentExecution).filter(AgentExecution.session_id == s.id).all()
        agent_times = [
            {
                "agent": e.agent_name,
                "duration_ms": e.duration_ms or 0,
                "status": e.status,
            }
            for e in execs
        ]

        result.append(
            {
                "session_id": s.id,
                "repo_id": s.repository_id,
                "status": s.status,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "retry_count": s.retry_count,
                "agent_breakdown": agent_times,
            }
        )
    return result


@router.get("/evaluation-metrics")
def evaluation_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """AI evaluation metrics (score, metric_name) if recorded."""
    session_ids = [
        s.id
        for s in db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .all()
    ]
    metrics = (
        db.query(EvaluationMetric)
        .filter(EvaluationMetric.session_id.in_(session_ids))
        .order_by(EvaluationMetric.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": m.id,
            "metric_name": m.metric_name,
            "score": m.score,
            "session_id": m.session_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in metrics
    ]
