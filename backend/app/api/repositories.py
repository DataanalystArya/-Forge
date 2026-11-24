from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.repository import Repository, IndexingJob
from app.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryListResponse

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.get("", response_model=RepositoryListResponse)
def list_repositories(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """List all repositories registered by the current user."""
    query = db.query(Repository).filter(Repository.user_id == current_user.id)
    total = query.count()
    repos = query.offset(skip).limit(limit).all()
    return RepositoryListResponse(
        items=[RepositoryResponse.model_validate(r) for r in repos],
        total=total
    )


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def create_repository(
    repo_in: RepositoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Register a new repository for analysis and monitoring."""
    existing = db.query(Repository).filter(
        Repository.user_id == current_user.id,
        Repository.full_name == repo_in.full_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository '{repo_in.full_name}' is already registered."
        )

    repo = Repository(
        user_id=current_user.id,
        full_name=repo_in.full_name,
        description=repo_in.description,
        default_branch=repo_in.default_branch,
        is_private=repo_in.is_private,
        clone_url=repo_in.clone_url or f"https://github.com/{repo_in.full_name}.git",
        status="REGISTERED"
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # Initialize a pending indexing job
    job = IndexingJob(
        repository_id=repo.id,
        status="QUEUED",
        indexed_files=0,
        total_files=0
    )
    db.add(job)
    db.commit()

    return RepositoryResponse.model_validate(repo)


@router.get("/{repo_id}", response_model=RepositoryResponse)
def get_repository(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Retrieve details of a single repository."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )
    return RepositoryResponse.model_validate(repo)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> None:
    """Delete a registered repository and its associated artifacts."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )
    db.delete(repo)
    db.commit()
    return None
