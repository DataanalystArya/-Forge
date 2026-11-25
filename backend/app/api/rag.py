"""
RAG API Router — Phase 3 Code RAG.

All endpoints require JWT authentication.
Repository ownership is verified on every request.

Endpoints:
  POST   /rag/repositories/{id}/index    — trigger indexing
  GET    /rag/repositories/{id}/status   — latest indexing run status
  POST   /rag/repositories/{id}/reindex  — force full re-index
  DELETE /rag/repositories/{id}/index    — delete chunks + vectors
  POST   /rag/search                     — hybrid / semantic / bm25 search
  POST   /rag/context                    — build LLM context from results
  GET    /rag/repositories/{id}/chunks   — paginated chunk listing
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.repository import Repository
from app.models.rag import CodeChunk
from app.models.user import User
from app.schemas.rag import (
    ChunkItem,
    ChunkListResponse,
    ContextRequest,
    ContextResponse,
    IndexRequest,
    IndexStatusResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)

logger = logging.getLogger("forge.api.rag")
router = APIRouter(prefix="/rag", tags=["RAG"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_owned_repo(repo_id: str, user: User, db: Session) -> Repository:
    """Return the repository or raise 404/403."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")
    if repo.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return repo


def _run_to_response(run, vec_svc=None) -> IndexStatusResponse:
    from app.services.vector_store_service import VectorStoreService

    if vec_svc is None:
        vec_svc = VectorStoreService.get_instance()

    available = vec_svc.is_available()
    mode = "unavailable"
    if available:
        mode = "memory" if vec_svc.is_memory_mode() else "server"

    return IndexStatusResponse(
        run_id=run.id,
        repository_id=run.repository_id,
        status=run.status,
        total_files=run.total_files or 0,
        processed_files=run.processed_files or 0,
        total_chunks=run.total_chunks or 0,
        embedded_chunks=run.embedded_chunks or 0,
        skipped_chunks=run.skipped_chunks or 0,
        error_message=run.error_message,
        embedding_model=run.embedding_model,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        vector_mode=mode,
        qdrant_available=available,
    )


# ---------------------------------------------------------------------------
# Indexing endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/repositories/{repository_id}/index",
    response_model=IndexStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger RAG indexing for a repository",
)
def trigger_index(
    repository_id: str,
    body: IndexRequest = IndexRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(repository_id, current_user, db)

    from app.services.rag_indexing_service import start_indexing

    try:
        run = start_indexing(
            repository_id=repository_id,
            user_id=current_user.id,
            db=db,
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return _run_to_response(run)


@router.post(
    "/repositories/{repository_id}/reindex",
    response_model=IndexStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Force full re-index (delete existing chunks first)",
)
def force_reindex(
    repository_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(repository_id, current_user, db)

    from app.services.rag_indexing_service import start_indexing

    run = start_indexing(
        repository_id=repository_id,
        user_id=current_user.id,
        db=db,
        force=True,
    )
    return _run_to_response(run)


@router.get(
    "/repositories/{repository_id}/status",
    response_model=IndexStatusResponse,
    summary="Get latest indexing run status",
)
def get_index_status(
    repository_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(repository_id, current_user, db)

    from app.services.rag_indexing_service import get_latest_run

    run = get_latest_run(repository_id, db)
    if not run:
        raise HTTPException(status_code=404, detail="No indexing run found for this repository.")
    return _run_to_response(run)


@router.delete(
    "/repositories/{repository_id}/index",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all chunks and vectors for a repository",
)
def delete_index(
    repository_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(repository_id, current_user, db)

    from app.services.vector_store_service import VectorStoreService
    from app.models.rag import IndexingRun

    # Delete DB chunks
    db.query(CodeChunk).filter(CodeChunk.repository_id == repository_id).delete()
    # Delete indexing runs
    db.query(IndexingRun).filter(IndexingRun.repository_id == repository_id).delete()
    db.commit()

    # Delete Qdrant vectors
    VectorStoreService.get_instance().delete_by_repository(repository_id)
    logger.info(f"Deleted index for repository {repository_id}.")


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search code chunks with hybrid / semantic / BM25 retrieval",
)
def search_code(
    body: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(body.repository_id, current_user, db)

    from app.services.retrieval_service import search_bm25, search_semantic, search_hybrid
    from app.services.vector_store_service import VectorStoreService
    from app.models.rag import RetrievalLog

    vec_svc = VectorStoreService.get_instance()
    available = vec_svc.is_available()
    vector_mode = "unavailable"
    if available:
        vector_mode = "memory" if vec_svc.is_memory_mode() else "server"

    t0 = time.monotonic()

    if body.method == "bm25":
        raw_results = search_bm25(body.query, body.repository_id, db, body.top_k)
    elif body.method == "semantic":
        raw_results = search_semantic(body.query, body.repository_id, body.top_k)
    else:
        raw_results = search_hybrid(body.query, body.repository_id, db, body.top_k)

    latency_ms = (time.monotonic() - t0) * 1000

    # Log the query
    try:
        log = RetrievalLog(
            user_id=current_user.id,
            repository_id=body.repository_id,
            query_text=body.query,
            results_count=len(raw_results),
            retrieval_method=body.method,
            latency_ms=latency_ms,
        )
        db.add(log)
        db.commit()
    except Exception:
        pass

    items = [
        SearchResultItem(
            chunk_id=r.chunk_id,
            repository_id=r.repository_id,
            file_path=r.file_path,
            symbol_name=r.symbol_name,
            symbol_type=r.symbol_type,
            start_line=r.start_line,
            end_line=r.end_line,
            language=r.language,
            chunk_content=r.chunk_content,
            score=r.score,
            retrieval_method=r.retrieval_method,
        )
        for r in raw_results
    ]

    return SearchResponse(
        query=body.query,
        method=body.method,
        results=items,
        total=len(items),
        latency_ms=round(latency_ms, 2),
        qdrant_available=available,
        vector_mode=vector_mode,
    )


# ---------------------------------------------------------------------------
# Context building endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/context",
    response_model=ContextResponse,
    summary="Assemble an LLM-ready context string from search results",
)
def build_context(
    body: ContextRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(body.repository_id, current_user, db)

    from app.services.retrieval_service import search_bm25, search_semantic, search_hybrid

    if body.method == "bm25":
        results = search_bm25(body.query, body.repository_id, db, body.top_k)
    elif body.method == "semantic":
        results = search_semantic(body.query, body.repository_id, body.top_k)
    else:
        results = search_hybrid(body.query, body.repository_id, db, body.top_k)

    # Assemble context with rough token budget (1 token ≈ 4 chars)
    char_budget = body.max_tokens * 4
    context_parts = []
    total_chars = 0

    for r in results:
        header = f"# File: {r.file_path} (lines {r.start_line}-{r.end_line})\n"
        body_text = f"```{r.language or ''}\n{r.chunk_content}\n```\n"
        block = header + body_text
        if total_chars + len(block) > char_budget:
            break
        context_parts.append(block)
        total_chars += len(block)

    context = "\n".join(context_parts)
    estimated_tokens = max(1, total_chars // 4)

    return ContextResponse(
        query=body.query,
        context=context,
        chunks_used=len(context_parts),
        estimated_tokens=estimated_tokens,
    )


# ---------------------------------------------------------------------------
# Chunk listing endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/repositories/{repository_id}/chunks",
    response_model=ChunkListResponse,
    summary="Paginated list of indexed code chunks",
)
def list_chunks(
    repository_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_repo(repository_id, current_user, db)

    total = db.query(CodeChunk).filter(CodeChunk.repository_id == repository_id).count()
    chunks = (
        db.query(CodeChunk)
        .filter(CodeChunk.repository_id == repository_id)
        .order_by(CodeChunk.file_path, CodeChunk.start_line)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ChunkListResponse(
        repository_id=repository_id,
        total=total,
        page=page,
        page_size=page_size,
        chunks=[ChunkItem.model_validate(c) for c in chunks],
    )
