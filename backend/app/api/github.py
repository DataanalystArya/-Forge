from datetime import datetime, timezone
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.core.encryption import encrypt_token, decrypt_token
from app.models.user import User, GitHubAccount, AuditLog
from app.services.github_service import GitHubService
from app.schemas.github import (
    GitHubConnectionStatus,
    GitHubConnectPATRequest,
    GitHubRepoItem,
    GitHubRepoListResponse,
)

router = APIRouter(prefix="/github", tags=["GitHub Integration"])


@router.get("/status", response_model=GitHubConnectionStatus)
def get_github_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """Check whether the current user has connected a GitHub account."""
    account = db.query(GitHubAccount).filter(GitHubAccount.user_id == current_user.id).first()
    if not account or not account.access_token_enc:
        return GitHubConnectionStatus(is_connected=False)
    
    return GitHubConnectionStatus(
        is_connected=True,
        username=account.username,
        avatar_url=account.avatar_url,
        github_user_id=account.github_user_id,
        connected_at=account.created_at
    )


@router.post("/connect-pat", response_model=GitHubConnectionStatus)
def connect_github_pat(
    payload: GitHubConnectPATRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """Securely connect GitHub using a Personal Access Token (classic or fine-grained)."""
    # 1. Validate token with GitHub API
    profile = GitHubService.get_user_profile(payload.token)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub token or insufficient permissions. Unable to fetch user profile."
        )

    # 2. Encrypt token for at-rest storage
    encrypted_tok = encrypt_token(payload.token)

    # 3. Upsert GitHubAccount
    account = db.query(GitHubAccount).filter(GitHubAccount.user_id == current_user.id).first()
    if not account:
        account = GitHubAccount(
            user_id=current_user.id,
            github_user_id=str(profile.get("id")),
            username=profile.get("login"),
            avatar_url=profile.get("avatar_url"),
            access_token_enc=encrypted_tok,
            scope="repo,read:user"
        )
        db.add(account)
    else:
        account.github_user_id = str(profile.get("id"))
        account.username = profile.get("login")
        account.avatar_url = profile.get("avatar_url")
        account.access_token_enc = encrypted_tok
        account.updated_at = datetime.now(timezone.utc)

    # 4. Audit Log (Never log tokens)
    audit = AuditLog(
        user_id=current_user.id,
        action="GITHUB_CONNECTED",
        target_type="GitHubAccount",
        target_id=str(profile.get("id")),
        details_json=f'{{"username": "{profile.get("login")}"}}'
    )
    db.add(audit)
    db.commit()
    db.refresh(account)

    return GitHubConnectionStatus(
        is_connected=True,
        username=account.username,
        avatar_url=account.avatar_url,
        github_user_id=account.github_user_id,
        connected_at=account.created_at
    )


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_github(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> None:
    """Disconnect GitHub account and purge stored credentials."""
    account = db.query(GitHubAccount).filter(GitHubAccount.user_id == current_user.id).first()
    if account:
        db.delete(account)
        audit = AuditLog(
            user_id=current_user.id,
            action="GITHUB_DISCONNECTED",
            target_type="GitHubAccount",
            target_id=account.id
        )
        db.add(audit)
        db.commit()
    return None


@router.get("/repos", response_model=GitHubRepoListResponse)
def list_github_repositories(
    page: int = 1,
    per_page: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """List accessible repositories from connected GitHub account."""
    account = db.query(GitHubAccount).filter(GitHubAccount.user_id == current_user.id).first()
    if not account or not account.access_token_enc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub account connected. Please connect your GitHub account first."
        )

    # Decrypt token safely in-memory only
    token = decrypt_token(account.access_token_enc)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt GitHub credentials. Please reconnect."
        )

    raw_repos = GitHubService.list_repositories(token, page=page, per_page=per_page)
    formatted = []
    for r in raw_repos:
        formatted.append(
            GitHubRepoItem(
                id=r.get("id"),
                name=r.get("name"),
                full_name=r.get("full_name"),
                description=r.get("description"),
                private=r.get("private", False),
                html_url=r.get("html_url"),
                clone_url=r.get("clone_url"),
                default_branch=r.get("default_branch", "main"),
                stargazers_count=r.get("stargazers_count", 0),
                language=r.get("language"),
                updated_at=r.get("updated_at")
            )
        )
    return GitHubRepoListResponse(repositories=formatted, total=len(formatted))
