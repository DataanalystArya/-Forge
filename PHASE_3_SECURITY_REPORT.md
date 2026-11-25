# FORGE — Phase 3 Security Report

## 1. Authentication & Authorization
- Every endpoint in `backend/app/api/rag.py` enforces JWT authentication via `Depends(get_current_user)` (`app.core.deps`).
- Every repository-scoped operation (`index`, `reindex`, `status`, `delete`, `search`, `context`, `chunks`) calls `_get_owned_repo(repo_id, current_user, db)`, returning `404` if missing and `403 Forbidden` if `repo.user_id != current_user.id`.
- Verified by `test_cross_user_isolation` and `test_search_unauthorized_repo`.

## 2. Tenant / Repository Isolation in Vector Store & DB
- Qdrant payloads store both `repository_id` and `user_id`.
- `VectorStoreService.search_semantic` always applies a mandatory `Filter(must=[FieldCondition(key="repository_id", match=MatchValue(value=repository_id))])` so vector queries cannot leak chunks across repositories.
- `RetrievalService.search_bm25` filters SQLAlchemy queries by `CodeChunk.repository_id == repository_id`.
- `CodeChunk`, `IndexingRun`, and `RetrievalLog` foreign keys cascade on repository/user deletion (`ondelete="CASCADE"`).

## 3. Static-Only Code Analysis (No Code Execution)
- `chunking_service.py` parses source files using `tree-sitter` and Python `ast.parse()` only. Repository code is never imported, `eval`'d, or executed in a subprocess.

## 4. Resource Exhaustion & Input Validation Guards
- Files larger than `2 MB` (`MAX_FILE_SIZE_BYTES`) are skipped before reading.
- Per-file chunk count is capped at `RAG_MAX_CHUNKS_PER_FILE` (500).
- Binary files (null-byte check) and ignored directories (`.git`, `node_modules`, `venv`, etc.) are excluded.
- `SearchRequest.query` is bounded (`min_length=1, max_length=500`) and `top_k` is bounded (`ge=1, le=50`), verified by `test_invalid_search_query_422`.
- Concurrent indexing on the same repository is blocked (`409 Conflict`).

## 5. Secrets & Logging Hygiene
- No API keys, JWTs, or GitHub PATs are stored in `CodeChunk`, `IndexingRun`, `RetrievalLog`, or Qdrant payloads.
- Retrieval logs record query text, counts, method, and latency only.
