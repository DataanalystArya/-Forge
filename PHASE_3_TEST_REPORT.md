# FORGE — Phase 3 Test Report

## 1. Backend Test Suite Execution
**Command executed:**
```bash
cd /Users/aryaverma/Downloads/Forge && PYTHONPATH=backend QDRANT_USE_MEMORY=true backend/venv/bin/pytest backend/tests -v --tb=short
```

**Result:** `38 passed in 9.70s` (0 failed, 0 skipped).

### Breakdown
- **Phase 1 & Security Audit tests** (`test_auth.py`, `test_database.py`, `test_repositories.py`, `test_audit_security.py`): **12 passed**
- **Phase 2 Explorer & GitHub tests** (`test_phase2_explorer.py`): **4 passed**
- **Phase 3 Code RAG tests** (`test_phase3_rag.py`): **22 passed**

### Phase 3 Test Cases Verified
1. `test_chunk_python_file_produces_symbols` — AST/Tree-sitter symbol chunking & SHA-256 hashes
2. `test_python_ast_extraction` — Function and class extraction with line bounds
3. `test_sliding_window_non_python` — Sliding-window chunking for Markdown/text files
4. `test_embedding_dimension` — Verified 384-dim output contract (mocked `SentenceTransformer` in offline sandbox)
5. `test_embedding_batch` — Verified batch encoding shape & non-zero vectors (mocked model)
6. `test_embedding_unavailable_raises` — Verified `EmbeddingUnavailableError` on missing model
7. `test_qdrant_upsert_and_search` — In-memory Qdrant upsert & `query_points` semantic retrieval
8. `test_bm25_search` — Code-aware BM25Plus lexical search over SQLite `code_chunks`
9. `test_bm25_empty_when_no_chunks` — Graceful empty list for unindexed repositories
10. `test_hybrid_search` — RRF fusion of semantic + BM25 results
11. `test_cross_user_isolation` — User B blocked (`403`) from indexing or searching User A's repository
12. `test_rag_index_trigger` — `POST /api/v1/rag/repositories/{id}/index` returns `202 Accepted`
13. `test_rag_status_404_no_run` — `GET /status` returns `404` before any indexing run
14. `test_rag_status_after_trigger` — `GET /status` returns `IndexingRun` metadata after trigger
15. `test_search_unauthorized_repo` — `POST /api/v1/rag/search` returns `403` for non-owners
16. `test_chunk_listing_endpoint` — `GET /chunks` returns paginated chunk records
17. `test_delete_index_endpoint` — `DELETE /index` returns `204` and deletes DB chunks
18. `test_duplicate_chunk_prevention` — Identical file content yields identical SHA-256 chunk hashes
19. `test_large_file_skipped` — Files > 2 MB are skipped by `chunk_file`
20. `test_invalid_search_query_422` — Empty query rejected with `422 Unprocessable Content`
21. `test_context_building_endpoint` — `POST /api/v1/rag/context` assembles token-budgeted context
22. `test_incremental_indexing_skips_unchanged` — Second `_run_indexing` skips unchanged chunks (`embedded_chunks == 0`, `skipped_chunks == total_chunks`)

*Note on mocks*: Because the execution sandbox has no outbound internet access to download HuggingFace weights, tests 4, 5, 7, 10, and 22 mock `SentenceTransformer` to return deterministic 384-dim numpy vectors while exercising all real chunking, SQLAlchemy, Qdrant `:memory:`, BM25Plus, and FastAPI code paths.

## 2. Frontend Production Build Verification
**Command executed:**
```bash
cd /Users/aryaverma/Downloads/Forge/frontend && npm run build
```

**Result:** Exited with code `0`.
- `✓ Compiled successfully`
- `✓ Linting and checking validity of types`
- `✓ Generating static pages (16/16)`
- `/code-search` compiled cleanly (`5.4 kB`, `109 kB` First Load JS).
