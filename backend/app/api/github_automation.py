"""Phase 7 — GitHub Automation API endpoints.

Requires explicit user approval before making any repository changes.
Never auto-merges.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.session import DebuggingSession, Patch, PullRequest
from app.models.repository import Repository
from app.services.git_service import GitService
from app.services.github_pr_service import GitHubPRService
from app.services.workspace_service import get_repo_workspace_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automation", tags=["github-automation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApprovePatchRequest(BaseModel):
    patch_id: str
    commit_message: str = ""
    branch_name: str = ""       # optional; generated if empty


class CreatePRRequest(BaseModel):
    session_id: str
    title: str
    body: str
    base_branch: str = "main"
    draft: bool = True           # Draft PRs by default — user must un-draft manually
    github_token: str            # PAT supplied at request time — never stored


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str, db: Session, user: User) -> DebuggingSession:
    s = db.query(DebuggingSession).filter(DebuggingSession.id == session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    if s.user_id != user.id:
        raise HTTPException(403, "Access denied")
    return s


def _get_patch_and_repo(patch_id: str, db: Session, user: User) -> tuple[Patch, Repository]:
    p = db.query(Patch).filter(Patch.id == patch_id).first()
    if not p:
        raise HTTPException(404, "Patch not found")
    s = db.query(DebuggingSession).filter(DebuggingSession.id == p.session_id).first()
    if not s or s.user_id != user.id:
        raise HTTPException(403, "Access denied")
    repo = db.query(Repository).filter(Repository.id == s.repository_id).first()
    if not repo:
        raise HTTPException(404, "Repository not found")
    return p, repo


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/approve")
def approve_and_apply_patch(
    session_id: str,
    req: ApprovePatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    **Explicit user approval gate.**

    Apply a patch to the workspace, create a commit, and return the diff.
    Does NOT push or create a PR automatically.
    """
    s = _get_session(session_id, db, current_user)
    patch, repo = _get_patch_and_repo(req.patch_id, db, current_user)

    workspace_path = get_repo_workspace_path(repo.id)
    if not workspace_path.exists():
        raise HTTPException(400, "Repository workspace not found or not cloned locally")

    git_svc = GitService(str(workspace_path))

    slug = re.sub(r"[^a-z0-9-]", "-", (repo.full_name or "repo").lower())
    branch = req.branch_name or f"forge/fix-{slug}-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    branch_result = (
        git_svc.create_branch(branch) if git_svc.available else {"ok": False, "error": "git not available"}
    )

    apply_result: dict = {"ok": True, "note": "no diff to apply"}
    if patch.diff_content and patch.diff_content.strip():
        apply_result = git_svc.apply_diff_patch(patch.diff_content)

    commit_result: dict = {"ok": False}
    if apply_result.get("ok"):
        msg = req.commit_message or f"forge: apply fix — iteration {patch.iteration}"
        commit_result = git_svc.commit_all(msg)

    if commit_result.get("ok"):
        patch.is_applied = True
        db.commit()

    return {
        "session_id": session_id,
        "patch_id": req.patch_id,
        "branch": branch,
        "branch_created": branch_result.get("ok", False),
        "patch_applied": apply_result.get("ok", False),
        "committed": commit_result.get("ok", False),
        "commit_sha": commit_result.get("sha"),
        "patch_apply_error": apply_result.get("error"),
        "note": "Branch created locally. Push manually or use create-pr endpoint to open a Pull Request.",
    }


@router.post("/sessions/{session_id}/create-pr")
def create_pull_request(
    session_id: str,
    req: CreatePRRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Create a GitHub Pull Request.

    Requires a GitHub PAT supplied by the user.
    Always creates as draft unless caller explicitly sets draft=False.
    **Never auto-merges.**
    """
    s = _get_session(session_id, db, current_user)
    repo = db.query(Repository).filter(Repository.id == s.repository_id).first()
    if not repo:
        raise HTTPException(404, "Repository not found")

    # Parse owner/repo from clone URL
    clone_url = getattr(repo, "clone_url", None) or getattr(repo, "url", None) or ""
    parts = clone_url.rstrip("/").rstrip(".git").split("/")
    if len(parts) < 2:
        raise HTTPException(400, "Cannot determine owner/repo from clone URL")
    owner, repo_name = parts[-2], parts[-1]

    # Must have applied patches
    patches = db.query(Patch).filter(Patch.session_id == session_id, Patch.is_applied == True).all()  # noqa: E712
    if not patches:
        raise HTTPException(400, "No applied patches found. Apply a patch first.")

    workspace_path = get_repo_workspace_path(repo.id)
    git_svc = GitService(str(workspace_path) if workspace_path.exists() else "")
    head_branch = git_svc.current_branch() if git_svc.available else "forge/fix"

    pr_svc = GitHubPRService(req.github_token)
    result = pr_svc.create_pull_request(
        owner=owner,
        repo=repo_name,
        title=req.title,
        body=req.body,
        head=head_branch,
        base=req.base_branch,
        draft=req.draft,
    )

    if result.get("ok"):
        pr_record = PullRequest(
            session_id=session_id,
            repository_id=repo.id,
            branch_name=head_branch,
            pr_number=result["pr_number"],
            pr_url=result["pr_url"],
            title=req.title,
            status="draft" if req.draft else "open",
        )
        db.add(pr_record)
        db.commit()

    return result


@router.get("/sessions/{session_id}/diff")
def get_session_diffs(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return all patch diffs for a session."""
    _get_session(session_id, db, current_user)
    patches = db.query(Patch).filter(Patch.session_id == session_id).order_by(Patch.created_at).all()
    return {
        "session_id": session_id,
        "patches": [
            {
                "patch_id": p.id,
                "iteration": p.iteration,
                "diff": p.diff_content or "",
                "rationale": p.rationale,
                "is_applied": p.is_applied,
            }
            for p in patches
        ],
    }


@router.get("/pull-requests")
def list_pull_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all pull requests from the current user's sessions."""
    session_ids = [
        s.id
        for s in db.query(DebuggingSession)
        .filter(DebuggingSession.user_id == current_user.id)
        .all()
    ]
    prs = (
        db.query(PullRequest)
        .filter(PullRequest.session_id.in_(session_ids))
        .order_by(PullRequest.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": pr.id,
            "session_id": pr.session_id,
            "repo_id": pr.repository_id,
            "branch": pr.branch_name,
            "pr_number": pr.pr_number,
            "pr_url": pr.pr_url,
            "title": pr.title,
            "status": pr.status,
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
        }
        for pr in prs
    ]
