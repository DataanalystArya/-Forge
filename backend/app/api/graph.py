"""Phase 5 — GraphRAG API endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.repository import Repository
from app.services.graph_service import GraphService
from app.services.workspace_service import get_repo_workspace_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["graph"])


def _get_repo(repo_id: str, db: Session, current_user: User) -> Repository:
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return repo


@router.post("/repositories/{repo_id}/extract")
def extract_graph(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Extract the code knowledge graph for *repo_id*.
    Walks the workspace directory and builds nodes/edges.
    """
    repo = _get_repo(repo_id, db, current_user)
    workspace_path = get_repo_workspace_path(repo.id)
    if not workspace_path.exists():
        raise HTTPException(status_code=400, detail="Repository workspace not found or not cloned locally")

    svc = GraphService.get_instance()
    result = svc.extract_code_graph(str(repo_id), str(workspace_path))
    return {
        "status": "ok",
        "repo_id": repo_id,
        "nodes_created": result["nodes"],
        "edges_created": result["edges"],
        "files_scanned": result["files_scanned"],
        "backend": result["backend"],
    }


@router.get("/repositories/{repo_id}/summary")
def graph_summary(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return node/edge counts for the repository's knowledge graph."""
    _get_repo(repo_id, db, current_user)
    svc = GraphService.get_instance()
    summary = svc.get_graph_summary(str(repo_id))
    return summary


@router.get("/repositories/{repo_id}/subgraph")
def subgraph(
    repo_id: str,
    symbol: str = "",
    depth: int = 2,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Return a React-Flow-compatible subgraph centred on *symbol*.
    """
    _get_repo(repo_id, db, current_user)
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol query parameter required")
    svc = GraphService.get_instance()
    return svc.query_subgraph(str(repo_id), symbol, min(depth, 4))


@router.get("/repositories/{repo_id}/context")
def graph_context(
    repo_id: str,
    query: str = "",
    limit: int = 8,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return graph context nodes that match *query* (for RAG augmentation)."""
    _get_repo(repo_id, db, current_user)
    if not query:
        raise HTTPException(status_code=400, detail="query parameter required")
    svc = GraphService.get_instance()
    return svc.query_context(str(repo_id), query, min(limit, 50))
