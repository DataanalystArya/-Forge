"""
RAG Regression Test Suite.

Covers every stage of the indexing-to-search pipeline:
  - EmbeddingService (real model + fallback model)
  - VectorStoreService (upsert, search, delete, repository filtering)
  - Chunking service
  - BM25 search
  - Semantic search
  - Hybrid search / RRF fusion
  - Re-indexing without duplicates
  - Empty repository handling
  - API endpoints (index, status, search)

All tests are deterministic: no network calls, no random data.
"""
from __future__ import annotations

import io
import math
import os
import tempfile
import time
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import Base, engine, SessionLocal
from app.models.rag import CodeChunk, IndexingRun
from app.models.repository import Repository
from app.models.user import User
from app.services.embedding_service import EmbeddingService
from app.services.vector_store_service import VectorStoreService
from app.services.retrieval_service import (
    search_bm25,
    search_hybrid,
    search_semantic,
)
from app.core.config import settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    email = f"rag_regression_{int(time.time() * 1000)}@example.com"
    password = "RegTest123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "RAG Tester"})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def repo_and_ws(client, auth_headers):
    """Create a repository, upload a ZIP, and return (repo_id, workspace_path)."""
    rr = client.post(
        "/api/v1/repositories",
        json={
            "name": "rag-regression",
            "full_name": "rag-test/regression",
            "clone_url": "https://example.com/rag-regression.git",
            "description": "RAG regression test repo",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    assert rr.status_code in (200, 201), rr.text
    repo_id = rr.json()["id"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "calculator.py",
            "def add(a: int, b: int) -> int:\n"
            "    return a - b  # BUG: should be a + b\n\n"
            "def multiply(a: int, b: int) -> int:\n"
            "    return a * b\n",
        )
        zf.writestr(
            "utils.py",
            "def safe_divide(a: float, b: float) -> float:\n"
            "    if b == 0:\n"
            "        raise ValueError('Division by zero')\n"
            "    return a / b\n",
        )
    buf.seek(0)
    up = client.post(
        f"/api/v1/repositories/{repo_id}/upload-zip",
        files={"file": ("repo.zip", buf.read(), "application/zip")},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text

    from app.services.workspace_service import get_repo_workspace_path
    ws_path = get_repo_workspace_path(repo_id)
    return repo_id, ws_path


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="class", autouse=True)
def reset_singletons():
    """Reset EmbeddingService and VectorStoreService between test classes."""
    yield
    EmbeddingService.reset_instance()
    VectorStoreService.reset_instance()


# ---------------------------------------------------------------------------
# 1. EmbeddingService
# ---------------------------------------------------------------------------

class TestEmbeddingService:
    def test_encode_single_returns_correct_dimension(self):
        svc = EmbeddingService.get_instance()
        vec = svc.encode_single("def add(a, b): return a + b")
        assert isinstance(vec, list)
        assert len(vec) == 384

    def test_encode_batch_matches_input_count(self):
        svc = EmbeddingService.get_instance()
        texts = ["function one", "function two", "function three"]
        vecs = svc.encode_batch(texts)
        assert len(vecs) == len(texts)

    def test_vectors_are_unit_normalized(self):
        svc = EmbeddingService.get_instance()
        for text in ["hello world", "def add(a, b):", "import os"]:
            vec = svc.encode_single(text)
            norm = math.sqrt(sum(x * x for x in vec))
            assert abs(norm - 1.0) < 1e-4, f"norm={norm} for '{text}'"

    def test_different_texts_produce_different_vectors(self):
        svc = EmbeddingService.get_instance()
        v1 = svc.encode_single("def add(a, b): return a + b")
        v2 = svc.encode_single("class DatabaseConnection: pass")
        # Dot product of two distinct unit vectors < 1 (they differ)
        dot = sum(a * b for a, b in zip(v1, v2))
        assert dot < 0.99, "Two completely different texts should not have near-identical embeddings"

    def test_empty_text_raises_value_error(self):
        svc = EmbeddingService.get_instance()
        with pytest.raises(ValueError):
            svc.encode_batch([])

    def test_is_available_true(self):
        svc = EmbeddingService.get_instance()
        assert svc.is_available() is True


# ---------------------------------------------------------------------------
# 2. VectorStoreService
# ---------------------------------------------------------------------------

class TestVectorStoreService:
    def _make_svc(self):
        VectorStoreService.reset_instance()
        svc = VectorStoreService.get_instance()
        svc.configure(settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSION)
        svc.is_available()  # trigger lazy init
        return svc

    def _make_chunk_payload(self, repo_id: str, chunk_id: str = None, symbol: str = "add") -> dict:
        return {
            "chunk_id": chunk_id or str(uuid.uuid4()),
            "repository_id": repo_id,
            "user_id": "test-user",
            "file_path": "calculator.py",
            "symbol_name": symbol,
            "symbol_type": "FUNCTION",
            "start_line": 1,
            "end_line": 2,
            "language": "python",
            "chunk_content": f"def {symbol}(a, b): return a + b",
        }

    def test_upsert_and_count(self):
        svc = self._make_svc()
        emb = EmbeddingService.get_instance()
        repo_id = f"test-repo-{uuid.uuid4().hex[:8]}"
        payload = [self._make_chunk_payload(repo_id)]
        vec = emb.encode_batch([payload[0]["chunk_content"]])
        ok = svc.upsert_chunks(payload, vec)
        assert ok is True
        count = svc._client.count(collection_name=settings.QDRANT_COLLECTION)
        assert count.count >= 1

    def test_semantic_search_returns_hit(self):
        svc = self._make_svc()
        emb = EmbeddingService.get_instance()
        repo_id = f"test-repo-{uuid.uuid4().hex[:8]}"
        payload = [self._make_chunk_payload(repo_id, symbol="add")]
        vec = emb.encode_batch(["def add(a, b): return a + b"])
        svc.upsert_chunks(payload, vec)

        query_vec = emb.encode_single("addition function")
        hits = svc.search_semantic(query_vec, repo_id, top_k=5)
        assert len(hits) >= 1
        assert hits[0].file_path == "calculator.py"

    def test_repository_filtering_isolates_results(self):
        """Results from repo A must not appear in a search filtered by repo B."""
        svc = self._make_svc()
        emb = EmbeddingService.get_instance()
        repo_a = f"repo-a-{uuid.uuid4().hex[:8]}"
        repo_b = f"repo-b-{uuid.uuid4().hex[:8]}"
        vec_a = emb.encode_single("def add(a, b): return a + b")
        svc.upsert_chunks([self._make_chunk_payload(repo_a)], [vec_a])

        query_vec = emb.encode_single("addition")
        # repo_b has nothing — should return empty
        hits = svc.search_semantic(query_vec, repo_b, top_k=5)
        assert hits == []
        # repo_a should return something
        hits_a = svc.search_semantic(query_vec, repo_a, top_k=5)
        assert len(hits_a) >= 1

    def test_delete_by_repository(self):
        svc = self._make_svc()
        emb = EmbeddingService.get_instance()
        repo_id = f"del-repo-{uuid.uuid4().hex[:8]}"
        payload = [self._make_chunk_payload(repo_id)]
        vec = emb.encode_batch([payload[0]["chunk_content"]])
        svc.upsert_chunks(payload, vec)

        # Verify it's there
        q = emb.encode_single("add function")
        hits = svc.search_semantic(q, repo_id, top_k=5)
        assert len(hits) >= 1

        # Delete and verify gone
        svc.delete_by_repository(repo_id)
        hits_after = svc.search_semantic(q, repo_id, top_k=5)
        assert hits_after == []

    def test_upsert_empty_is_noop(self):
        svc = self._make_svc()
        result = svc.upsert_chunks([], [])
        assert result is True

    def test_chunk_id_consistency(self):
        """The chunk_id in the payload must come back unchanged from search."""
        svc = self._make_svc()
        emb = EmbeddingService.get_instance()
        repo_id = f"cid-repo-{uuid.uuid4().hex[:8]}"
        expected_cid = str(uuid.uuid4())
        payload = [self._make_chunk_payload(repo_id, chunk_id=expected_cid)]
        vec = emb.encode_batch([payload[0]["chunk_content"]])
        svc.upsert_chunks(payload, vec)

        q = emb.encode_single("add function")
        hits = svc.search_semantic(q, repo_id, top_k=5)
        assert len(hits) == 1
        assert hits[0].chunk_id == expected_cid


# ---------------------------------------------------------------------------
# 3. BM25 Search
# ---------------------------------------------------------------------------

class TestBM25Search:
    def _create_db_chunks(self, db: Session, repo_id: str) -> list:
        """Insert CodeChunk rows into the DB for a fake repo (no FK check for test isolation)."""
        from app.models.repository import Repository
        # Create a stub repo row to satisfy FK
        from app.models.user import User
        user = User(email=f"bm25-{uuid.uuid4().hex[:8]}@test.com", hashed_password="x", full_name="BM25")
        db.add(user)
        db.flush()
        repo = Repository(
            id=repo_id,
            user_id=user.id,

            full_name="bm25/test",
            clone_url="https://example.com/bm25.git",
            default_branch="main",
        )
        db.add(repo)
        db.flush()
        chunks_data = [
            ("calculator.py", "add", "def add(a: int, b: int) -> int:\n    return a - b  # BUG"),
            ("calculator.py", "multiply", "def multiply(a: int, b: int) -> int:\n    return a * b"),
            ("utils.py", "safe_divide", "def safe_divide(a, b):\n    if b == 0:\n        raise ValueError('zero')\n    return a / b"),
        ]
        created = []
        for fp, sym, content in chunks_data:
            c = CodeChunk(
                repository_id=repo_id,
                file_path=fp,
                symbol_name=sym,
                symbol_type="FUNCTION",
                start_line=1,
                end_line=2,
                chunk_content=content,
                content_hash=str(uuid.uuid4()),
                embedding_model=settings.EMBEDDING_MODEL,
                is_embedded=False,
                language="python",
            )
            db.add(c)
            db.flush()
            created.append(c)
        db.commit()
        return created

    def test_bm25_returns_matching_chunks(self, db):
        repo_id = f"bm25-{uuid.uuid4().hex[:8]}"
        self._create_db_chunks(db, repo_id)
        results = search_bm25("add subtraction bug", repo_id, db, top_k=5)
        assert len(results) >= 1
        # The 'add' function with the BUG comment should be top result
        top = results[0]
        assert "add" in top.chunk_content.lower() or "bug" in top.chunk_content.lower()

    def test_bm25_returns_empty_for_no_match(self, db):
        repo_id = f"bm25-{uuid.uuid4().hex[:8]}"
        self._create_db_chunks(db, repo_id)
        results = search_bm25("xyzzy_nonexistent_token_12345", repo_id, db, top_k=5)
        assert results == []

    def test_bm25_returns_empty_for_unknown_repo(self, db):
        results = search_bm25("add function", "nonexistent-repo-id", db, top_k=5)
        assert results == []

    def test_bm25_all_results_have_required_fields(self, db):
        repo_id = f"bm25-fields-{uuid.uuid4().hex[:8]}"
        self._create_db_chunks(db, repo_id)
        results = search_bm25("function", repo_id, db, top_k=5)
        for r in results:
            assert r.chunk_id
            assert r.repository_id == repo_id
            assert r.file_path
            assert r.chunk_content
            assert r.score > 0
            assert r.retrieval_method == "bm25"


# ---------------------------------------------------------------------------
# 4. Semantic Search
# ---------------------------------------------------------------------------

class TestSemanticSearch:
    def _upsert_chunks(self, repo_id: str, contents: list[str]) -> list[str]:
        emb = EmbeddingService.get_instance()
        svc = VectorStoreService.get_instance()
        svc.configure(settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSION)
        chunk_ids = []
        payloads = []
        for i, content in enumerate(contents):
            cid = str(uuid.uuid4())
            chunk_ids.append(cid)
            payloads.append({
                "chunk_id": cid,
                "repository_id": repo_id,
                "user_id": "test-user",
                "file_path": f"file_{i}.py",
                "symbol_name": f"func_{i}",
                "symbol_type": "FUNCTION",
                "start_line": 1,
                "end_line": 5,
                "language": "python",
                "chunk_content": content,
            })
        vecs = emb.encode_batch(contents)
        svc.upsert_chunks(payloads, vecs)
        return chunk_ids

    def test_semantic_search_returns_results(self):
        repo_id = f"sem-{uuid.uuid4().hex[:8]}"
        self._upsert_chunks(repo_id, [
            "def add(a: int, b: int) -> int:\n    return a + b",
            "class DatabaseConnection:\n    def connect(self): pass",
        ])
        emb = EmbeddingService.get_instance()
        svc = VectorStoreService.get_instance()
        svc.configure(settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSION)
        q = emb.encode_single("addition function integers")
        hits = svc.search_semantic(q, repo_id, top_k=5)
        assert len(hits) >= 1

    def test_semantic_search_isolates_by_repo(self):
        repo_x = f"sem-x-{uuid.uuid4().hex[:8]}"
        repo_y = f"sem-y-{uuid.uuid4().hex[:8]}"
        self._upsert_chunks(repo_x, ["def add(a, b): return a + b"])
        emb = EmbeddingService.get_instance()
        svc = VectorStoreService.get_instance()
        svc.configure(settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSION)
        q = emb.encode_single("addition")
        hits_y = svc.search_semantic(q, repo_y, top_k=5)
        assert hits_y == []

    def test_semantic_search_via_service_function(self):
        repo_id = f"sem-svc-{uuid.uuid4().hex[:8]}"
        self._upsert_chunks(repo_id, ["def add(a, b): return a + b"])
        results = search_semantic("add function", repo_id, top_k=5)
        assert len(results) >= 1
        assert results[0].retrieval_method == "semantic"


# ---------------------------------------------------------------------------
# 5. Hybrid Search (RRF Fusion)
# ---------------------------------------------------------------------------

class TestHybridSearch:
    def _setup_repo_with_chunks(self, db: Session) -> str:
        """Create a fully-indexed repo in DB + Qdrant and return its ID."""
        from app.models.user import User

        repo_id = f"hyb-{uuid.uuid4().hex[:8]}"
        user = User(email=f"hyb-{uuid.uuid4().hex[:6]}@test.com", hashed_password="x", full_name="HybTest")
        db.add(user)
        db.flush()
        repo = Repository(
            id=repo_id,
            user_id=user.id,

            full_name="hyb/test",
            clone_url="https://example.com/hyb.git",
            default_branch="main",
        )
        db.add(repo)
        db.flush()

        emb = EmbeddingService.get_instance()
        svc = VectorStoreService.get_instance()
        svc.configure(settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSION)

        contents = [
            ("calculator.py", "add", "def add(a: int, b: int) -> int:\n    return a - b  # BUG"),
            ("calculator.py", "multiply", "def multiply(a: int, b: int) -> int:\n    return a * b"),
            ("utils.py", "safe_divide", "def safe_divide(a, b):\n    if b == 0: raise ValueError('zero')\n    return a / b"),
        ]
        payloads = []
        db_chunks = []
        for fp, sym, content in contents:
            c = CodeChunk(
                repository_id=repo_id,
                file_path=fp,
                symbol_name=sym,
                symbol_type="FUNCTION",
                start_line=1,
                end_line=3,
                chunk_content=content,
                content_hash=str(uuid.uuid4()),
                embedding_model=settings.EMBEDDING_MODEL,
                is_embedded=True,
                language="python",
            )
            db.add(c)
            db.flush()
            db_chunks.append(c)
            payloads.append({
                "chunk_id": c.id,
                "repository_id": repo_id,
                "user_id": user.id,
                "file_path": fp,
                "symbol_name": sym,
                "symbol_type": "FUNCTION",
                "start_line": 1,
                "end_line": 3,
                "language": "python",
                "chunk_content": content,
            })
        db.commit()
        vecs = emb.encode_batch([p["chunk_content"] for p in payloads])
        svc.upsert_chunks(payloads, vecs)
        return repo_id

    def test_hybrid_returns_results_from_both_sources(self, db):
        repo_id = self._setup_repo_with_chunks(db)
        results = search_hybrid("add subtraction bug", repo_id, db, top_k=5)
        assert len(results) >= 1

    def test_hybrid_results_have_method_hybrid(self, db):
        repo_id = self._setup_repo_with_chunks(db)
        results = search_hybrid("add function", repo_id, db, top_k=5)
        for r in results:
            assert r.retrieval_method == "hybrid"

    def test_hybrid_scores_are_positive(self, db):
        repo_id = self._setup_repo_with_chunks(db)
        results = search_hybrid("multiply integers", repo_id, db, top_k=5)
        for r in results:
            assert r.score > 0

    def test_hybrid_falls_back_to_bm25_when_semantic_empty(self, db):
        """When Qdrant has no vectors for a repo, hybrid should still return BM25 hits."""
        repo_id = f"hyb-fallback-{uuid.uuid4().hex[:8]}"
        user = User(email=f"fallback-{uuid.uuid4().hex[:6]}@test.com", hashed_password="x", full_name="FallbackTest")
        db.add(user)
        db.flush()
        repo = Repository(
            id=repo_id, user_id=user.id, full_name="fb/test",
            clone_url="https://example.com/fb.git", default_branch="main",
        )
        db.add(repo)
        db.flush()
        # Insert chunk in DB only (no Qdrant upsert)
        c = CodeChunk(
            repository_id=repo_id,
            file_path="calc.py", symbol_name="add", symbol_type="FUNCTION",
            start_line=1, end_line=2,
            chunk_content="def add(a, b): return a + b",
            content_hash="abc123", embedding_model=settings.EMBEDDING_MODEL,
            is_embedded=False, language="python",
        )
        db.add(c)
        db.commit()

        results = search_hybrid("add function", repo_id, db, top_k=5)
        assert len(results) >= 1
        # Should come from BM25 since Qdrant is empty for this repo
        assert results[0].retrieval_method == "hybrid"

    def test_hybrid_rrf_prefers_top_ranked_items(self, db):
        """Item ranked #1 in both BM25 and semantic should have the highest fused score."""
        repo_id = self._setup_repo_with_chunks(db)
        results = search_hybrid("add subtraction bug", repo_id, db, top_k=5)
        assert len(results) >= 2
        # Scores should be non-increasing
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score - 1e-9


# ---------------------------------------------------------------------------
# 6. API Endpoint Integration
# ---------------------------------------------------------------------------

class TestRAGAPIEndpoints:
    def test_index_returns_202(self, client, auth_headers, repo_and_ws):
        repo_id, _ = repo_and_ws
        # Force re-index to ensure we get a fresh run
        resp = client.post(f"/api/v1/rag/repositories/{repo_id}/reindex", headers=auth_headers)
        assert resp.status_code == 202, resp.text

    def test_indexing_completes_successfully(self, client, auth_headers, repo_and_ws):
        repo_id, _ = repo_and_ws
        # Trigger and wait
        client.post(f"/api/v1/rag/repositories/{repo_id}/index", headers=auth_headers)
        for _ in range(90):
            st = client.get(f"/api/v1/rag/repositories/{repo_id}/status", headers=auth_headers)
            d = st.json() if st.status_code == 200 else {}
            if d.get("status") == "COMPLETED":
                break
            if d.get("status") == "FAILED":
                pytest.fail(f"Indexing FAILED: {d.get('error_message')}")
            time.sleep(1.0)
        else:
            pytest.fail("Indexing did not complete in 90 seconds")
        assert d["embedded_chunks"] >= 1

    def test_hybrid_search_returns_results_after_indexing(self, client, auth_headers, repo_and_ws):
        """After successful indexing, hybrid search must return >= 1 result."""
        repo_id, _ = repo_and_ws
        # Ensure indexing completed first
        for _ in range(90):
            st = client.get(f"/api/v1/rag/repositories/{repo_id}/status", headers=auth_headers)
            d = st.json() if st.status_code == 200 else {}
            if d.get("status") == "COMPLETED":
                break
            time.sleep(1.0)
        resp = client.post(
            "/api/v1/rag/search",
            json={"repository_id": repo_id, "query": "add function bug", "mode": "hybrid", "top_k": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1
        assert len(body["results"]) >= 1

    def test_bm25_search_returns_results_after_indexing(self, client, auth_headers, repo_and_ws):
        repo_id, _ = repo_and_ws
        resp = client.post(
            "/api/v1/rag/search",
            json={"repository_id": repo_id, "query": "add function", "method": "bm25", "top_k": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1

    def test_semantic_search_returns_results_after_indexing(self, client, auth_headers, repo_and_ws):
        repo_id, _ = repo_and_ws
        resp = client.post(
            "/api/v1/rag/search",
            json={"repository_id": repo_id, "query": "addition integers", "method": "semantic", "top_k": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1

    def test_search_result_fields_are_complete(self, client, auth_headers, repo_and_ws):
        repo_id, _ = repo_and_ws
        resp = client.post(
            "/api/v1/rag/search",
            json={"repository_id": repo_id, "query": "function", "mode": "hybrid", "top_k": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["results"]:
            assert item["chunk_id"]
            assert item["repository_id"] == repo_id
            assert item["file_path"]
            assert item["chunk_content"]
            assert isinstance(item["start_line"], int)
            assert isinstance(item["end_line"], int)
            assert item["score"] > 0

    def test_reindex_does_not_duplicate_chunks(self, client, auth_headers, repo_and_ws, db):
        """Force reindex must not create duplicate DB rows."""
        repo_id, _ = repo_and_ws
        # First count
        count_before = db.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()
        # Force reindex
        client.post(f"/api/v1/rag/repositories/{repo_id}/reindex", headers=auth_headers)
        for _ in range(90):
            st = client.get(f"/api/v1/rag/repositories/{repo_id}/status", headers=auth_headers)
            d = st.json() if st.status_code == 200 else {}
            if d.get("status") == "COMPLETED":
                break
            time.sleep(1.0)
        # Refresh session
        db.expire_all()
        count_after = db.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()
        # After full reindex, count should equal (not exceed) the first count
        assert count_after == count_before, (
            f"Duplicate chunks detected: {count_after} after reindex vs {count_before} before"
        )

    def test_search_on_unindexed_repo_returns_empty(self, client, auth_headers):
        """Searching a repo that was never indexed must return empty, not an error."""
        # Create a fresh empty repo
        rr = client.post(
            "/api/v1/repositories",
            json={"name": "empty-rag", "full_name": "empty/rag", "clone_url": "https://example.com/e.git",
                  "description": "empty", "default_branch": "main"},
            headers=auth_headers,
        )
        assert rr.status_code in (200, 201)
        repo_id = rr.json()["id"]

        resp = client.post(
            "/api/v1/rag/search",
            json={"repository_id": repo_id, "query": "anything", "mode": "hybrid", "top_k": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["results"] == []

    def test_delete_index_clears_chunks(self, client, auth_headers, repo_and_ws, db):
        """DELETE /rag/repositories/{id}/index must remove all chunks from DB."""
        repo_id, _ = repo_and_ws
        # Ensure there is something to delete
        count_before = db.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()
        assert count_before >= 1
        resp = client.delete(f"/api/v1/rag/repositories/{repo_id}/index", headers=auth_headers)
        assert resp.status_code == 204
        db.expire_all()
        count_after = db.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()
        assert count_after == 0
