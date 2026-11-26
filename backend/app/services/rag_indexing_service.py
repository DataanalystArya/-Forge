"""
RAG Indexing Service — Phase 3 Code RAG.

Orchestrates the full pipeline:
  File discovery → Chunking → Dedup via hash → Embedding → Qdrant upsert
  → BM25 warmup (implicit via DB) → IndexingRun status tracking.

Runs the heavy work in a background thread so the API endpoint returns
immediately after creating an IndexingRun record.

Key guarantees:
- Incremental: only re-embeds files whose content_hash changed.
- Removes stale chunks (deleted files).
- Prevents concurrent indexing of the same repository.
- Never executes repository code.
- Never fabricates embeddings.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("forge.rag_indexing")


def _get_workspace_dir(repository) -> Optional[str]:
    """Resolve the workspace directory from the repository record."""
    import os
    # Check the standard workspace path
    base = os.path.join(os.getcwd(), "workspaces", repository.id)
    if os.path.isdir(base):
        return base
    # Fallback: scan workspaces dir
    ws_root = os.path.join(os.getcwd(), "workspaces")
    if os.path.isdir(ws_root):
        for entry in os.listdir(ws_root):
            candidate = os.path.join(ws_root, entry)
            if entry == repository.id and os.path.isdir(candidate):
                return candidate
    return None


def _run_indexing(run_id: str, repository_id: str, user_id: str, force: bool) -> None:
    """
    Background thread: performs chunking + embedding + Qdrant upsert.

    Opens its own DB session so it doesn't share state with the request session.
    """
    from app.core.database import SessionLocal
    from app.models.rag import IndexingRun, CodeChunk
    from app.models.repository import Repository
    from app.services.chunking_service import chunk_repository
    from app.services.embedding_service import EmbeddingService, EmbeddingUnavailableError
    from app.services.vector_store_service import VectorStoreService
    from app.services.retrieval_service import invalidate_bm25_cache
    from app.core.config import settings

    db: Session = SessionLocal()
    try:
        run = db.query(IndexingRun).filter(IndexingRun.id == run_id).first()
        if not run:
            return

        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc)
        run.embedding_model = settings.EMBEDDING_MODEL
        db.commit()

        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repo:
            _fail(db, run, "Repository not found.")
            return

        workspace_dir = _get_workspace_dir(repo)
        if not workspace_dir:
            _fail(db, run, "No cloned workspace found. Clone or upload the repository first.")
            return

        # ------------------------------------------------------------------
        # 1. Chunk the repository
        # ------------------------------------------------------------------
        logger.info(f"[{run_id}] Chunking repository '{repo.full_name}' at {workspace_dir}…")
        new_chunks = chunk_repository(
            workspace_dir,
            max_lines=settings.RAG_CHUNK_MAX_LINES,
            overlap=settings.RAG_CHUNK_OVERLAP_LINES,
            max_chunks_per_file=settings.RAG_MAX_CHUNKS_PER_FILE,
        )

        run.total_files = len({c.file_path for c in new_chunks})
        db.commit()

        if not new_chunks:
            _fail(db, run, "No indexable chunks found in this repository.")
            return

        # ------------------------------------------------------------------
        # 2. Incremental dedup — compare content hashes against stored chunks
        # ------------------------------------------------------------------
        if force:
            # Full re-index: delete everything first
            db.query(CodeChunk).filter(CodeChunk.repository_id == repository_id).delete()
            db.commit()
            VectorStoreService.get_instance().delete_by_repository(repository_id)
            invalidate_bm25_cache(repository_id)
            existing_hashes: dict[str, str] = {}
        else:
            existing = (
                db.query(CodeChunk.id, CodeChunk.file_path, CodeChunk.start_line, CodeChunk.content_hash)
                .filter(CodeChunk.repository_id == repository_id)
                .all()
            )
            # Map (file_path, start_line) → content_hash
            existing_hashes: dict[str, str] = {
                f"{row.file_path}:{row.start_line}": row.content_hash
                for row in existing
            }

        # Files that still exist in this indexing run
        current_file_paths = {c.file_path for c in new_chunks}

        # Remove stale chunks (files deleted from repo)
        if not force and existing_hashes:
            existing_files = {k.split(":")[0] for k in existing_hashes}
            stale_files = existing_files - current_file_paths
            if stale_files:
                for stale_fp in stale_files:
                    db.query(CodeChunk).filter(
                        CodeChunk.repository_id == repository_id,
                        CodeChunk.file_path == stale_fp,
                    ).delete()
                    VectorStoreService.get_instance().delete_by_file(repository_id, stale_fp)
                db.commit()

        # Filter to only new/changed chunks
        chunks_to_embed = []
        skipped = 0
        for c in new_chunks:
            key = f"{c.file_path}:{c.start_line}"
            if existing_hashes.get(key) == c.content_hash:
                skipped += 1
                continue
            chunks_to_embed.append(c)

        run.total_chunks = len(new_chunks)
        run.skipped_chunks = skipped
        run.processed_files = len(current_file_paths)
        db.commit()

        logger.info(
            f"[{run_id}] {len(chunks_to_embed)} new/changed chunks "
            f"({skipped} unchanged, skipping)."
        )

        # ------------------------------------------------------------------
        # 3. Embedding + Qdrant upsert (batched)
        # ------------------------------------------------------------------
        emb_svc = EmbeddingService.get_instance(settings.EMBEDDING_MODEL)
        vec_svc = VectorStoreService.get_instance()
        vec_svc.configure(settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSION)

        embedded_count = 0
        batch_size = settings.RAG_BATCH_SIZE

        for i in range(0, len(chunks_to_embed), batch_size):
            batch = chunks_to_embed[i : i + batch_size]
            texts = [c.chunk_content for c in batch]

            try:
                vectors = emb_svc.encode_batch(texts, batch_size=batch_size)
            except EmbeddingUnavailableError as exc:
                _fail(db, run, f"Embedding model unavailable: {exc}")
                return

            # Batch lookup of existing chunks to avoid 32x roundtrips per batch
            batch_file_paths = {c.file_path for c in batch}
            existing_chunks_batch = (
                db.query(CodeChunk)
                .filter(
                    CodeChunk.repository_id == repository_id,
                    CodeChunk.file_path.in_(batch_file_paths),
                )
                .all()
            )
            existing_map = {
                (c.file_path, c.start_line, c.symbol_name): c
                for c in existing_chunks_batch
            }

            qdrant_payloads = []
            new_chunk_objs = []

            for chunk_data, vector in zip(batch, vectors):
                key = (chunk_data.file_path, chunk_data.start_line, chunk_data.symbol_name)
                existing_chunk = existing_map.get(key)

                if existing_chunk:
                    existing_chunk.chunk_content = chunk_data.chunk_content
                    existing_chunk.content_hash = chunk_data.content_hash
                    existing_chunk.end_line = chunk_data.end_line
                    existing_chunk.is_embedded = True
                    existing_chunk.embedding_model = settings.EMBEDDING_MODEL
                    chunk_id = existing_chunk.id
                else:
                    new_chunk = CodeChunk(
                        repository_id=repository_id,
                        file_path=chunk_data.file_path,
                        language=chunk_data.language,
                        symbol_name=chunk_data.symbol_name,
                        symbol_type=chunk_data.symbol_type,
                        start_line=chunk_data.start_line,
                        end_line=chunk_data.end_line,
                        chunk_content=chunk_data.chunk_content,
                        content_hash=chunk_data.content_hash,
                        embedding_model=settings.EMBEDDING_MODEL,
                        is_embedded=True,
                    )
                    db.add(new_chunk)
                    new_chunk_objs.append((new_chunk, chunk_data, vector))
                    chunk_id = None  # Will be assigned after single bulk flush

                if chunk_id is not None:
                    qdrant_payloads.append({
                        "chunk_id": chunk_id,
                        "repository_id": repository_id,
                        "user_id": user_id,
                        "file_path": chunk_data.file_path,
                        "symbol_name": chunk_data.symbol_name,
                        "symbol_type": chunk_data.symbol_type,
                        "start_line": chunk_data.start_line,
                        "end_line": chunk_data.end_line,
                        "language": chunk_data.language,
                        "chunk_content": chunk_data.chunk_content,
                    })

            # Single flush for all newly inserted chunks in this batch
            if new_chunk_objs:
                db.flush()
                for new_chunk, chunk_data, vector in new_chunk_objs:
                    qdrant_payloads.append({
                        "chunk_id": new_chunk.id,
                        "repository_id": repository_id,
                        "user_id": user_id,
                        "file_path": chunk_data.file_path,
                        "symbol_name": chunk_data.symbol_name,
                        "symbol_type": chunk_data.symbol_type,
                        "start_line": chunk_data.start_line,
                        "end_line": chunk_data.end_line,
                        "language": chunk_data.language,
                        "chunk_content": chunk_data.chunk_content,
                    })

            vec_svc.upsert_chunks(qdrant_payloads, vectors)
            db.commit()
            embedded_count += len(batch)

            run.embedded_chunks = embedded_count
            db.commit()
            logger.debug(f"[{run_id}] Batch {i // batch_size + 1} done: {embedded_count} embedded.")

        # ------------------------------------------------------------------
        # 4. Mark run COMPLETED
        # ------------------------------------------------------------------
        run.status = "COMPLETED"
        run.embedded_chunks = embedded_count
        run.completed_at = datetime.now(timezone.utc)
        invalidate_bm25_cache(repository_id)
        db.commit()

        logger.info(
            f"[{run_id}] Indexing complete: {embedded_count} chunks embedded, "
            f"{skipped} skipped, vector_mode={'memory' if vec_svc.is_memory_mode() else 'server'}."
        )

    except Exception as exc:
        logger.error(f"[{run_id}] Unexpected indexing error: {exc}", exc_info=True)
        try:
            run = db.query(IndexingRun).filter(IndexingRun.id == run_id).first()
            if run:
                _fail(db, run, str(exc))
        except Exception:
            pass
    finally:
        db.close()


def _fail(db: Session, run, message: str) -> None:
    run.status = "FAILED"
    run.error_message = message
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.error(f"Indexing run {run.id} FAILED: {message}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_indexing(
    repository_id: str,
    user_id: str,
    db: Session,
    force: bool = False,
) -> "IndexingRun":
    """
    Create an IndexingRun record and launch background indexing.

    Args:
        repository_id: ID of the repository to index.
        user_id: ID of the owning user (injected into Qdrant payload for filtering).
        db: SQLAlchemy session (for creating the run record only).
        force: If True, delete all existing chunks and re-embed everything.

    Returns:
        The newly created IndexingRun (status=PENDING → RUNNING in background).

    Raises:
        ValueError: if a run is already in progress.
    """
    from app.models.rag import IndexingRun

    # Prevent duplicate concurrent runs
    active = (
        db.query(IndexingRun)
        .filter(
            IndexingRun.repository_id == repository_id,
            IndexingRun.status.in_(["PENDING", "RUNNING"]),
        )
        .first()
    )
    if active and not force:
        raise ValueError("An indexing run is already in progress for this repository.")

    run = IndexingRun(
        repository_id=repository_id,
        status="PENDING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_id = run.id
    t = threading.Thread(
        target=_run_indexing,
        args=(run_id, repository_id, user_id, force),
        daemon=True,
        name=f"rag-index-{run_id[:8]}",
    )
    t.start()

    return run


def get_latest_run(repository_id: str, db: Session) -> Optional["IndexingRun"]:
    """Return the most recent IndexingRun for a repository."""
    from app.models.rag import IndexingRun

    return (
        db.query(IndexingRun)
        .filter(IndexingRun.repository_id == repository_id)
        .order_by(IndexingRun.created_at.desc())
        .first()
    )
