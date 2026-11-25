# FORGE — Phase 3 Report: Code RAG & Semantic Repository Intelligence

## 1. Overview
Phase 3 implements FORGE's Code Retrieval-Augmented Generation (RAG) and Semantic Repository Intelligence layer, enabling authenticated users to index repositories into AST-aware code chunks, generate local dense embeddings, and run semantic, lexical (BM25), or hybrid (Reciprocal Rank Fusion) searches across their repositories.

## 2. Architecture & Implemented Components

### 2.1 Database Models (`backend/app/models/rag.py`)
- **`CodeChunk`**: Stores `id`, `repository_id` (FK -> `repositories.id` ON DELETE CASCADE), `file_path`, `language`, `symbol_name`, `symbol_type`, `start_line`, `end_line`, `chunk_content`, `content_hash` (SHA-256), `embedding_model`, `is_embedded`, and timestamps. Includes `UniqueConstraint("repository_id", "file_path", "symbol_name", "start_line")`.
- **`IndexingRun`**: Tracks Phase 3 RAG indexing jobs (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`), file counts, `total_chunks`, `embedded_chunks`, `skipped_chunks`, `embedding_model`, and `error_message`.
- **`RetrievalLog`**: Records `user_id`, `repository_id`, `query_text`, `results_count`, `retrieval_method`, and `latency_ms`.

### 2.2 Code Chunking Engine (`backend/app/services/chunking_service.py`)
- Reuses `IGNORED_DIRECTORIES`, `IGNORED_EXTENSIONS`, `LANGUAGE_MAP`, `is_binary_file`, `extract_python_symbols_ast`, `extract_python_symbols_treesitter`, and `extract_ts_js_symbols_simple` from `scanner_service.py`.
- Extracts function/class/method chunks for Python (Tree-sitter + AST fallback) and JS/TS.
- Splits oversized symbols (> `RAG_CHUNK_MAX_LINES`, default 80) and non-parsed text files into overlapping sliding-window chunks (`RAG_CHUNK_OVERLAP_LINES`, default 10).
- Skips binary files, ignored directories, and files > 2 MB (`MAX_FILE_SIZE_BYTES`).
- Computes SHA-256 `content_hash` per chunk for incremental deduplication.

### 2.3 Local Embedding Service (`backend/app/services/embedding_service.py`)
- Thread-safe lazy singleton `EmbeddingService` wrapping `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions, normalized embeddings).
- Raises `EmbeddingUnavailableError` if the model cannot be loaded — never substitutes random or fake vectors.

### 2.4 Qdrant Vector Store Service (`backend/app/services/vector_store_service.py`)
- Thread-safe singleton `VectorStoreService` wrapping `qdrant-client`.
- Connects to `settings.QDRANT_URL` (`http://localhost:6333`) by default and falls back automatically to `QdrantClient(":memory:")` when a Qdrant server is unreachable or `QDRANT_USE_MEMORY=True`.
- Uses `query_points` with mandatory `repository_id` payload filter and deterministic UUIDv5 point ID mapping for non-UUID chunk IDs.

### 2.5 Hybrid Retrieval Service (`backend/app/services/retrieval_service.py`)
- **BM25 (`search_bm25`)**: Uses `rank_bm25.BM25Plus` with a code-aware tokenizer (`_tokenize`) that splits on punctuation and `snake_case` boundaries, filtering out zero-overlap documents.
- **Semantic (`search_semantic`)**: Encodes the query via `EmbeddingService` and queries `VectorStoreService`.
- **Hybrid (`search_hybrid`)**: Combines semantic and BM25 rankings using weighted Reciprocal Rank Fusion (RRF, `semantic_weight=0.6`, `bm25_weight=0.4`), falling back cleanly if either source returns empty.

### 2.6 Incremental Indexing Pipeline (`backend/app/services/rag_indexing_service.py`)
- Runs asynchronously in a background daemon thread (`start_indexing`).
- Prevents concurrent indexing runs on the same repository (returns 409 Conflict).
- Compares `content_hash` values to skip unchanged chunks, removes stale chunks for deleted files, and supports `force=True` full re-indexing.

### 2.7 API Endpoints (`backend/app/api/rag.py`, prefix `/api/v1/rag`)
- `POST /repositories/{repository_id}/index` — Trigger incremental or forced indexing (`202 Accepted`)
- `POST /repositories/{repository_id}/reindex` — Force full re-index (`202 Accepted`)
- `GET /repositories/{repository_id}/status` — Latest `IndexingRun` status & vector mode (`200` / `404`)
- `DELETE /repositories/{repository_id}/index` — Delete DB chunks, runs, and Qdrant vectors (`204 No Content`)
- `POST /search` — Hybrid / semantic / BM25 search (`200`)
- `POST /context` — Token-budgeted LLM context builder (`200`)
- `GET /repositories/{repository_id}/chunks` — Paginated chunk listing (`200`)

### 2.8 Frontend Code Intelligence UI (`frontend/src/app/(dashboard)/code-search/page.tsx`)
- Repository selector dropdown, indexing trigger & Force re-index controls, live polling status badge (`server` vs `memory` Qdrant mode, chunk progress bar), search method toggle (`HYBRID`, `SEMANTIC`, `BM25`), `top_k` selector, expandable code cards, and deep-links to `/repositories/[id]?file=...`.

## 3. Local Run Commands
```bash
# Backend
cd /Users/aryaverma/Downloads/Forge
PYTHONPATH=backend QDRANT_USE_MEMORY=true backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd /Users/aryaverma/Downloads/Forge/frontend
npm run dev
```

## 4. Known Limitations
- **Qdrant server**: Docker is not installed in the current environment; `VectorStoreService` runs in `QdrantClient(":memory:")` fallback mode (vectors do not persist across backend restarts unless a Qdrant server is running at `QDRANT_URL`).
- **Offline model download**: In network-restricted environments without a cached HuggingFace model, `all-MiniLM-L6-v2` cannot be downloaded on first run (`EmbeddingService` raises `EmbeddingUnavailableError`; BM25 lexical search continues working).
- **Cross-Encoder Reranking**: Not yet implemented; hybrid retrieval currently uses weighted RRF.
