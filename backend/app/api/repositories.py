import os
from pathlib import Path
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.encryption import decrypt_token
from app.models.user import User, GitHubAccount
from app.models.repository import Repository, IndexingJob, CodeArtifact
from app.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryListResponse
from app.schemas.explorer import FileTreeNode, FileContentResponse, ArtifactItemResponse, ArtifactListResponse
from app.services.workspace_service import (
    clone_repository,
    extract_zip_archive,
    get_repo_workspace_path,
    WorkspaceSecurityError,
)
from app.services.scanner_service import (
    RepositoryScanner,
    LANGUAGE_MAP,
    IGNORED_DIRECTORIES,
    IGNORED_EXTENSIONS,
)

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
    """Delete a registered repository and its associated workspace directory."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )
    
    # Clean workspace directory on disk
    try:
        workspace_path = get_repo_workspace_path(repo.id)
        if workspace_path.exists():
            import shutil
            shutil.rmtree(workspace_path, ignore_errors=True)
    except Exception:
        pass

    db.delete(repo)
    db.commit()
    return None


@router.post("/{repo_id}/clone", response_model=RepositoryResponse)
def clone_and_scan_repository(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Clone remote repository into workspace and execute structural scanner."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    if not repo.clone_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Repository has no clone URL configured.")

    # Check for connected GitHub token if private
    access_token = None
    account = db.query(GitHubAccount).filter(GitHubAccount.user_id == current_user.id).first()
    if account and account.access_token_enc:
        access_token = decrypt_token(account.access_token_enc)

    try:
        workspace_dir = clone_repository(repo.id, repo.clone_url, access_token=access_token)
        repo = RepositoryScanner.scan_repository(repo, workspace_dir, db)
        return RepositoryResponse.model_validate(repo)
    except WorkspaceSecurityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cloning failed: {str(e)}")


@router.post("/{repo_id}/upload-zip", response_model=RepositoryResponse)
async def upload_zip_repository(
    repo_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Safely upload and extract a ZIP archive of source code, then execute scanner."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .zip archives are supported.")

    content = await file.read()
    try:
        workspace_dir, count = extract_zip_archive(repo.id, content)
        repo = RepositoryScanner.scan_repository(repo, workspace_dir, db)
        return RepositoryResponse.model_validate(repo)
    except WorkspaceSecurityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Archive processing failed: {str(e)}")


def _build_tree(current_dir: Path, workspace_root: Path) -> List[FileTreeNode]:
    """Recursively build directory tree structure."""
    nodes: List[FileTreeNode] = []
    try:
        items = sorted(os.listdir(current_dir))
    except Exception:
        return nodes

    for item in items:
        if item in IGNORED_DIRECTORIES:
            continue
        item_path = current_dir / item
        rel_path = str(item_path.relative_to(workspace_root))

        if item_path.is_dir():
            children = _build_tree(item_path, workspace_root)
            nodes.append(
                FileTreeNode(
                    name=item,
                    path=rel_path,
                    type="directory",
                    children=children
                )
            )
        elif item_path.is_file():
            ext = item_path.suffix.lower()
            if ext in IGNORED_EXTENSIONS:
                continue
            nodes.append(
                FileTreeNode(
                    name=item,
                    path=rel_path,
                    type="file",
                    size=item_path.stat().st_size if item_path.exists() else 0,
                    language=LANGUAGE_MAP.get(ext, "Other")
                )
            )
    return nodes


@router.get("/{repo_id}/tree", response_model=List[FileTreeNode])
def get_repository_file_tree(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Return the nested file and folder tree of the ingested repository."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    workspace_dir = get_repo_workspace_path(repo.id)
    if not workspace_dir.exists():
        return []

    return _build_tree(workspace_dir, workspace_dir)


@router.get("/{repo_id}/file", response_model=FileContentResponse)
def get_repository_file_content(
    repo_id: str,
    path: str = Query(..., description="Relative path of file inside repository"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Retrieve the content of a single source file with path traversal validation."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    workspace_dir = get_repo_workspace_path(repo.id)
    if not workspace_dir.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Repository has not been ingested yet.")

    # Guard against Path Traversal
    safe_rel_path = os.path.normpath(path).lstrip("/")
    target_file = (workspace_dir / safe_rel_path).resolve()

    if not str(target_file).startswith(str(workspace_dir.resolve())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path traversal detected.")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{path}' not found.")

    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to read file: {e}")

    ext = target_file.suffix.lower()
    return FileContentResponse(
        path=safe_rel_path,
        name=target_file.name,
        language=LANGUAGE_MAP.get(ext, "Plain Text"),
        size=target_file.stat().st_size,
        lines=len(content.splitlines()),
        content=content
    )


@router.get("/{repo_id}/symbols", response_model=ArtifactListResponse)
def get_repository_symbols(
    repo_id: str,
    entity_type: Optional[str] = Query(None, description="Filter by CLASS, FUNCTION, or FILE"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """List extracted AST code artifacts and symbols for the repository."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id,
        Repository.user_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    query = db.query(CodeArtifact).filter(CodeArtifact.repository_id == repo.id)
    if entity_type:
        query = query.filter(CodeArtifact.entity_type == entity_type)

    total = query.count()
    artifacts = query.offset(skip).limit(limit).all()

    return ArtifactListResponse(
        artifacts=[
            ArtifactItemResponse(
                id=a.id,
                file_path=a.file_path,
                language=a.language,
                entity_type=a.entity_type,
                entity_name=a.entity_name,
                start_line=a.start_line,
                end_line=a.end_line
            )
            for a in artifacts
        ],
        total=total
    )
