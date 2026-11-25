# FORGE — Phase 3 Real-World Verification Report

## 1. Environment Used
- **OS**: macOS (ARM64), Python 3.14.5 (`backend/venv/`), Node.js v20 / Next.js 14.2.35
- **Backend**: FastAPI + Uvicorn (`http://127.0.0.1:8000`), SQLite (`forge.db`), `HF_HUB_OFFLINE=1` (after initial HuggingFace weight download)
- **Frontend**: Next.js production server (`npm run start`, `http://localhost:3000`)
- **Vector Store**: Qdrant (`qdrant-client`) in `:memory:` fallback mode (`QDRANT_USE_MEMORY=true`)
- **Docker**: Not available (`docker not found`, `qdrant not found`)

## 2. Model & Embedding Verification — **VERIFIED**
- Loaded real `sentence-transformers` model `all-MiniLM-L6-v2` (downloaded `model.safetensors`, 90.9 MB, no mocks).
- `EmbeddingService.get_dimension()` returned **`384`**.
- `EmbeddingService.encode_single("def authenticate_user(username, password): pass")` returned a real 384-dim normalized float vector (sample first 5 dims: `[-0.038332756608724594, 0.02445349469780922, -0.09064643830060959, -0.05849889665842056, -0.09001918137073517]`).

## 3. Qdrant Persistent Server Connectivity — **FAILED / UNAVAILABLE (Fallback Verified)**
- Probed `http://localhost:6333/collections` -> connection failed; `docker` and `qdrant` binaries are not installed in this environment.
- In-memory fallback (`QdrantClient(":memory:")`) was verified separately and operated cleanly (`vector_mode: "memory"`, `qdrant_available: true`).
- **Limitation**: Vectors stored in `:memory:` mode do not persist across backend restarts without a running Qdrant server.

## 4. Repository Tested — **VERIFIED**
- Connected public GitHub repository **`pallets/markupsafe`** (`https://github.com/pallets/markupsafe.git`, repo ID `2703f709-4795-412e-a026-9b3576260b71`) via Phase 2 `POST /api/v1/repositories` and `POST /api/v1/repositories/{id}/clone`.
- Phase 2 scanner reported `status: READY`, `total_files: 44`, `total_lines: 3847`.

## 5. Indexing & Storage Results — **VERIFIED**
- Triggered `POST /api/v1/rag/repositories/2703f709-4795-412e-a026-9b3576260b71/index`.
- Run `63c43df8-6e48-4c84-9f95-f4ad677095fd` completed: `total_files: 42`, `processed_files: 42`, `total_chunks: 182`, `embedded_chunks: 182`, `skipped_chunks: 0`, `embedding_model: all-MiniLM-L6-v2`.
- Confirmed `182` `CodeChunk` rows persisted in `forge.db` with `is_embedded: true` and valid SHA-256 `content_hash`.

## 6. Search Queries & Actual Results — **VERIFIED**
All returned chunks were checked against actual files on disk (`disk_exact_match=True` for every result):

1. **SEMANTIC** (`"escape HTML special characters safely"`, `941.96ms`):
   - `docs/index.rst` `L1-52` (`BLOCK:None`, score `0.6137`)
   - `src/markupsafe/_native.py` `L1-8` (`FUNCTION:_escape_inner`, score `0.6096`)
   - `src/markupsafe/__init__.py` `L188-197` (`FUNCTION:unescape`, score `0.5929`)
2. **BM25** (`"escape"`, `18.35ms`):
   - `bench.py` `L1-30` (`BLOCK:None`, score `4.2270`)
   - `src/markupsafe/__init__.py` `L367-389` (`CLASS:_MarkupEscapeHelper`, score `4.1895`)
   - `src/markupsafe/__init__.py` `L48-61` (`FUNCTION:escape_silent`, score `4.1760`)
3. **HYBRID** (`"class Markup escape"`, `510.98ms`):
   - `src/markupsafe/__init__.py` `L84-163` (`CLASS:Markup`, score `0.0163`)
   - `src/markupsafe/__init__.py` `L24-45` (`FUNCTION:escape`, score `0.0154`)
   - `docs/escaping.rst` `L1-21` (`BLOCK:None`, score `0.0097`)

## 7. Incremental Indexing Results — **VERIFIED**
- **Re-index unchanged repo (Run 2)**: `total_chunks: 182`, `skipped_chunks: 181`, `embedded_chunks: 1`, total DB chunks remained `182` (0 duplicates created). *(Note: 1 chunk re-embedded because `existing_hashes` in `rag_indexing_service.py` keys by `file_path:start_line`, which collides when two AST/block items share a starting line.)*
- **Add new file (`src/markupsafe/_verify_temp.py`, Run 3)**: `total_files: 43`, `total_chunks: 183`; hybrid search for `forge_verify_temp_fn` returned `('src/markupsafe/_verify_temp.py', 'forge_verify_temp_fn', 1, 3)`.
- **Modify file (Run 4)**: `total_chunks: 183`; search for `"modified verification function"` returned the updated chunk containing `"modified:"`.
- **Delete file (Run 5)**: `total_files: 42`, `total_chunks: 182`; `0` stale DB chunks and `0` stale search hits remained for `_verify_temp.py`.

## 8. Security Verification — **VERIFIED**
Authenticated second user (`verify_other@forge.dev`) attempted access to User A's repository `2703f709-4795-412e-a026-9b3576260b71`:
- `GET /api/v1/rag/repositories/{id}/status` -> **`403`**
- `GET /api/v1/rag/repositories/{id}/chunks` -> **`403`**
- `POST /api/v1/rag/search` -> **`403`**
- `POST /api/v1/rag/repositories/{id}/index` -> **`403`**
- `DELETE /api/v1/rag/repositories/{id}/index` -> **`403`**

## 9. Frontend Verification — **UNVERIFIED (Interrupted)**
- The Next.js production server was started on `http://localhost:3000` and `/code-search` was compiled cleanly in `npm run build`.
- Interactive browser subagent verification of `/code-search` was started (`9aba050e-df9a-4b14-b9dd-cd012eef2ba1`) but interrupted when continuing directly to Phases 4–9; full UI verification will be completed in Phase 9 End-to-End testing.

## 10. Failures & Limitations
- **Qdrant Persistent Server**: Unavailable (Docker/Qdrant not installed on host); verified via `:memory:` fallback.
- **Minor Observation**: Keying `existing_hashes` by `f"{file_path}:{start_line}"` caused 1/182 chunks to re-embed on an unchanged re-index (no duplicate rows created).
