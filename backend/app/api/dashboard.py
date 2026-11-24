from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.repository import Repository, IndexingJob
from app.models.session import DebuggingSession, TestExecution, Patch, PullRequest

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Calculate and return live, genuine dashboard metrics from the database."""
    # 1. Total connected repositories
    total_repos = db.query(func.count(Repository.id)).filter(
        Repository.user_id == current_user.id
    ).scalar() or 0

    # 2. Total debugging sessions
    total_sessions = db.query(func.count(DebuggingSession.id)).filter(
        DebuggingSession.user_id == current_user.id
    ).scalar() or 0

    # 3. Active debugging sessions (not completed or failed)
    active_sessions = db.query(func.count(DebuggingSession.id)).filter(
        DebuggingSession.user_id == current_user.id,
        DebuggingSession.status.notin_(["COMPLETED", "FAILED"])
    ).scalar() or 0

    # 4. Total tests executed & pass rate calculation
    user_session_ids = [s.id for s in db.query(DebuggingSession.id).filter(
        DebuggingSession.user_id == current_user.id
    ).all()]

    total_tests_passed = 0
    total_tests_failed = 0
    if user_session_ids:
        test_stats = db.query(
            func.sum(TestExecution.passed_count),
            func.sum(TestExecution.failed_count)
        ).filter(TestExecution.session_id.in_(user_session_ids)).first()
        total_tests_passed = test_stats[0] or 0
        total_tests_failed = test_stats[1] or 0

    total_test_evaluations = total_tests_passed + total_tests_failed
    test_pass_rate = round(
        (total_tests_passed / total_test_evaluations * 100), 1
    ) if total_test_evaluations > 0 else 0.0

    # 5. Total pull requests generated
    total_prs = 0
    if user_session_ids:
        total_prs = db.query(func.count(PullRequest.id)).filter(
            PullRequest.session_id.in_(user_session_ids)
        ).scalar() or 0

    # 6. Recent sessions
    recent_sessions = db.query(DebuggingSession).filter(
        DebuggingSession.user_id == current_user.id
    ).order_by(DebuggingSession.created_at.desc()).limit(5).all()

    return {
        "total_repositories": total_repos,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_tests_passed": total_tests_passed,
        "total_tests_failed": total_tests_failed,
        "test_pass_rate": test_pass_rate,
        "total_pull_requests": total_prs,
        "recent_sessions": [
            {
                "id": s.id,
                "title": s.title,
                "status": s.status,
                "current_phase": s.current_phase,
                "repository_id": s.repository_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in recent_sessions
        ]
    }
