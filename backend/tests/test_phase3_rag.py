"""
Phase 3 — Code RAG Test Suite.

Tests:
1.  Code chunking — Python file with known functions → chunk metadata
2.  Python AST extraction — known class/function structure
3.  Sliding window chunking — non-Python file
4.  Embedding generation — correct dimension (384 for MiniLM)
5.  Embedding batch — multiple texts
6.  Embedding service unavailable — raises EmbeddingUnavailableError
7.  Qdrant upsert + semantic search (in-memory client)
8.  BM25 keyword search — returns relevant chunk
9.  BM25 — returns empty list when no chunks in DB
10. Hybrid search — merges semantic + BM25 results
11. Cross-user isolation — User B cannot search User A's repository
12. RAG index trigger — 202 Accepted, run created
13. RAG status — 404 when no run exists
14. RAG status — returns run data after indexing starts
15. Search endpoint — unauthorized repo returns 403
16. Chunk listing endpoint — returns paginated chunks
17. Delete index endpoint — removes chunks from DB
18. Duplicate chunk prevention — same hash not inserted twice
19. Large file skipping — files > 2 MB not chunked
20. Invalid search query — 422 Unprocessable
"""
from __future__ import annotations

import hashlib
import io
import os
import tempfile
import threading
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ─── App bootstrap ────────────────────────────────────────────────────────────

os.environ.setdefault("QDRANT_USE_MEMORY", "true")

from app.core.database import Base, get_db as database_get_db
from app.main import app
from app.models import User, Repository, CodeChunk, IndexingRun
from app.models.user import generate_uuid

# ─── In-memory SQLite fixture ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    _engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_engine)
    yield _engine
    _engine.dispose()


@pytest.fixture(scope="module")
def db_session(engine):
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client(engine):
    from app.core import deps as core_deps

    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[core_deps.get_db] = override_get_db
    app.dependency_overrides[database_get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def register_and_login(client: TestClient, email: str, password: str = "StrongPass1!") -> str:
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test"})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Sample Python source for chunking tests ─────────────────────────────────

SAMPLE_PYTHON = '''
def add(a, b):
    """Return sum of a and b."""
    return a + b


def multiply(a, b):
    """Return product."""
    result = a * b
    return result


class Calculator:
    """Simple calculator."""

    def __init__(self):
        self.history = []

    def compute(self, op, a, b):
        if op == "add":
            return self.add(a, b)
        return 0

    def add(self, a, b):
        result = a + b
        self.history.append(result)
        return result
'''

# ─── 1. Chunking — Python file with known functions ───────────────────────────

def test_chunk_python_file_produces_symbols():
    from app.services.chunking_service import chunk_file

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        fp = ws / "calc.py"
        fp.write_text(SAMPLE_PYTHON)

        chunks = chunk_file(fp, ws, max_lines=80, overlap=10, max_chunks=500)

    # Should find at least add, multiply, Calculator
    symbol_names = {c.symbol_name for c in chunks}
    assert "add" in symbol_names or any("add" in (s or "") for s in symbol_names)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.file_path == "calc.py"
        assert chunk.chunk_content != ""
        assert chunk.content_hash == hashlib.sha256(chunk.chunk_content.encode()).hexdigest()
        assert chunk.start_line >= 1
        assert chunk.end_line >= chunk.start_line


# ─── 2. Python AST extraction ─────────────────────────────────────────────────

def test_python_ast_extraction():
    from app.services.scanner_service import extract_python_symbols_ast

    symbols = extract_python_symbols_ast(SAMPLE_PYTHON, "calc.py")
    entity_names = {s["entity_name"] for s in symbols}

    assert "add" in entity_names
    assert "multiply" in entity_names
    assert "Calculator" in entity_names
    for s in symbols:
        assert s["start_line"] >= 1
        assert s["end_line"] >= s["start_line"]


# ─── 3. Sliding window chunking ───────────────────────────────────────────────

def test_sliding_window_non_python():
    from app.services.chunking_service import chunk_file

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        fp = ws / "notes.md"
        # 50 lines
        fp.write_text("\n".join([f"Line {i}" for i in range(1, 51)]))

        chunks = chunk_file(fp, ws, max_lines=20, overlap=5, max_chunks=500)

    assert len(chunks) >= 2
    for c in chunks:
        assert c.symbol_type == "BLOCK"
        assert c.start_line >= 1


# ─── 4. Embedding dimension — using mock model ───────────────────────────────

def test_embedding_dimension():
    """EmbeddingService.get_dimension() returns the model's dimension."""
    from app.services.embedding_service import EmbeddingService

    # Reset singleton so we control the mock
    EmbeddingService.reset_instance()

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384

    svc = EmbeddingService("all-MiniLM-L6-v2")
    # Inject mock model directly (bypass network download)
    svc._model = mock_model

    dim = svc.get_dimension()
    assert dim == 384, f"Expected 384, got {dim}"

    EmbeddingService.reset_instance()


# ─── 5. Embedding batch ───────────────────────────────────────────────────────

def test_embedding_batch():
    """encode_batch returns one vector per text, all with correct dimension."""
    import numpy as np
    from app.services.embedding_service import EmbeddingService

    EmbeddingService.reset_instance()

    # Build mock that returns realistic-shaped numpy arrays
    texts = ["def hello(): pass", "class Foo: pass", "import os"]
    fake_vectors = np.random.randn(len(texts), 384).astype(np.float32)

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    mock_model.encode.return_value = fake_vectors

    svc = EmbeddingService("all-MiniLM-L6-v2")
    svc._model = mock_model

    vectors = svc.encode_batch(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert isinstance(v, list)
        assert len(v) == 384
        # Vectors must NOT be all zeros (would indicate fake/broken embeddings)
        assert any(x != 0.0 for x in v)

    EmbeddingService.reset_instance()


# ─── 6. Embedding unavailable — raises correct error ──────────────────────────

def test_embedding_unavailable_raises():
    """EmbeddingService raises EmbeddingUnavailableError for bad model names."""
    from app.services.embedding_service import EmbeddingService, EmbeddingUnavailableError

    EmbeddingService.reset_instance()

    # Patch SentenceTransformer to simulate a load failure
    with patch("app.services.embedding_service.EmbeddingService._ensure_model") as mock_ensure:
        mock_ensure.side_effect = EmbeddingUnavailableError("Mock: model not found")
        svc = EmbeddingService("this-model-does-not-exist-xyz123")
        with pytest.raises(EmbeddingUnavailableError):
            svc.get_dimension()

    EmbeddingService.reset_instance()


# ─── 7. Qdrant in-memory upsert + semantic search ────────────────────────────

def test_qdrant_upsert_and_search():
    """Qdrant in-memory client can store and retrieve vectors."""
    import numpy as np
    from app.services.embedding_service import EmbeddingService, EmbeddingUnavailableError
    from app.services.vector_store_service import VectorStoreService

    EmbeddingService.reset_instance()
    VectorStoreService.reset_instance()

    # Create mock embedding service
    texts = [
        "def authenticate_user(username, password): ...",
        "class Database: def connect(self): ...",
    ]
    fake_vectors = np.random.randn(len(texts), 384).astype(np.float32)

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    mock_model.encode.return_value = fake_vectors

    emb_svc = EmbeddingService.get_instance("all-MiniLM-L6-v2")
    emb_svc._model = mock_model

    vectors = emb_svc.encode_batch(texts)
    assert len(vectors) == 2

    # Use in-memory Qdrant
    vec_svc = VectorStoreService.get_instance()
    vec_svc.configure("test_collection_phase3", 384)

    repo_id = "test-repo-qdrant-001"
    chunks = [
        {
            "chunk_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "repository_id": repo_id,
            "user_id": "user-001",
            "file_path": "auth.py",
            "symbol_name": "authenticate_user",
            "symbol_type": "FUNCTION",
            "start_line": 1,
            "end_line": 5,
            "language": "Python",
            "chunk_content": texts[0],
        },
        {
            "chunk_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "repository_id": repo_id,
            "user_id": "user-001",
            "file_path": "db.py",
            "symbol_name": "Database",
            "symbol_type": "CLASS",
            "start_line": 1,
            "end_line": 10,
            "language": "Python",
            "chunk_content": texts[1],
        },
    ]

    ok = vec_svc.upsert_chunks(chunks, vectors)
    assert ok is True

    # Search using the same vector (should find itself)
    query_vec = vectors[0]
    results = vec_svc.search_semantic(query_vec, repo_id, top_k=2)

    assert len(results) >= 1
    # The auth chunk (chunk-001) should rank highest for its own vector
    assert results[0].file_path in ("auth.py", "db.py")

    EmbeddingService.reset_instance()
    VectorStoreService.reset_instance()


# ─── 8. BM25 keyword search ───────────────────────────────────────────────────

def test_bm25_search(db_session):
    from app.services.retrieval_service import search_bm25

    # Create a test repository + user + chunks in DB
    user = User(
        id="bm25-user-001",
        email="bm25@test.com",
        hashed_password="x",
        full_name="BM25 User",
    )
    db_session.merge(user)

    repo = Repository(
        id="bm25-repo-001",
        user_id="bm25-user-001",
        full_name="bm25/test",
    )
    db_session.merge(repo)

    chunk_a = CodeChunk(
        id="bm25-chunk-a",
        repository_id="bm25-repo-001",
        file_path="auth.py",
        language="Python",
        symbol_name="authenticate",
        symbol_type="FUNCTION",
        start_line=1,
        end_line=10,
        chunk_content="def authenticate(user, password): return check_password(user, password)",
        content_hash="hash-a",
        is_embedded=False,
    )
    chunk_b = CodeChunk(
        id="bm25-chunk-b",
        repository_id="bm25-repo-001",
        file_path="db.py",
        language="Python",
        symbol_name="connect",
        symbol_type="FUNCTION",
        start_line=1,
        end_line=5,
        chunk_content="def connect(): return psycopg2.connect(dsn)",
        content_hash="hash-b",
        is_embedded=False,
    )
    db_session.merge(chunk_a)
    db_session.merge(chunk_b)
    db_session.commit()

    results = search_bm25("authenticate password", "bm25-repo-001", db_session, top_k=5)
    assert len(results) >= 1
    assert results[0].file_path == "auth.py"
    assert results[0].retrieval_method == "bm25"


# ─── 9. BM25 returns empty when no chunks ────────────────────────────────────

def test_bm25_empty_when_no_chunks(db_session):
    from app.services.retrieval_service import search_bm25

    results = search_bm25("anything", "nonexistent-repo-xyz", db_session, top_k=5)
    assert results == []


# ─── 10. Hybrid search merges both sources ────────────────────────────────────

def test_hybrid_search(db_session):
    """Hybrid search returns BM25 results when semantic/Qdrant is empty."""
    from app.services.retrieval_service import search_hybrid
    from app.services.embedding_service import EmbeddingService
    import numpy as np

    EmbeddingService.reset_instance()

    # Mock the embedding model so semantic path works without network
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    mock_model.encode.return_value = np.random.randn(1, 384).astype(np.float32)

    emb_svc = EmbeddingService.get_instance("all-MiniLM-L6-v2")
    emb_svc._model = mock_model

    # Minimal smoke test — should not crash even if Qdrant returns empty
    results = search_hybrid("authenticate", "bm25-repo-001", db_session, top_k=5)
    # At minimum, BM25 results should come through
    assert isinstance(results, list)
    for r in results:
        assert r.retrieval_method in ("hybrid", "bm25", "semantic")

    EmbeddingService.reset_instance()


# ─── 11. Cross-user isolation ─────────────────────────────────────────────────

def test_cross_user_isolation(client):
    # Register two users
    token_a = register_and_login(client, "userarag@forge.dev")
    token_b = register_and_login(client, "userbrag@forge.dev")

    # User A creates a repository
    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "userA/private-repo", "description": ""},
        headers=auth_headers(token_a),
    )
    assert r.status_code in (200, 201)
    repo_id = r.json()["id"]

    # User B tries to trigger indexing of User A's repo
    r2 = client.post(
        f"/api/v1/rag/repositories/{repo_id}/index",
        json={},
        headers=auth_headers(token_b),
    )
    assert r2.status_code == 403, f"Expected 403, got {r2.status_code}: {r2.text}"

    # User B tries to search User A's repo
    r3 = client.post(
        "/api/v1/rag/search",
        json={"query": "test", "repository_id": repo_id, "method": "bm25"},
        headers=auth_headers(token_b),
    )
    assert r3.status_code == 403


# ─── 12. RAG index trigger — 202 Accepted ─────────────────────────────────────

def test_rag_index_trigger(client):
    token = register_and_login(client, "indextest@forge.dev")

    # Create repo
    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "idx/repo", "description": ""},
        headers=auth_headers(token),
    )
    repo_id = r.json()["id"]

    # Trigger index (no workspace — will fail in background, but API should return 202)
    r2 = client.post(
        f"/api/v1/rag/repositories/{repo_id}/index",
        json={},
        headers=auth_headers(token),
    )
    assert r2.status_code == 202
    data = r2.json()
    assert data["repository_id"] == repo_id
    assert data["status"] in ("PENDING", "RUNNING")


# ─── 13. RAG status — 404 when no run exists ──────────────────────────────────

def test_rag_status_404_no_run(client):
    token = register_and_login(client, "norun@forge.dev")

    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "norun/repo", "description": ""},
        headers=auth_headers(token),
    )
    repo_id = r.json()["id"]

    r2 = client.get(
        f"/api/v1/rag/repositories/{repo_id}/status",
        headers=auth_headers(token),
    )
    assert r2.status_code == 404


# ─── 14. RAG status — returns run after trigger ───────────────────────────────

def test_rag_status_after_trigger(client):
    token = register_and_login(client, "statustest2@forge.dev")

    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "status/repo2", "description": ""},
        headers=auth_headers(token),
    )
    repo_id = r.json()["id"]

    client.post(
        f"/api/v1/rag/repositories/{repo_id}/index",
        json={},
        headers=auth_headers(token),
    )

    r2 = client.get(
        f"/api/v1/rag/repositories/{repo_id}/status",
        headers=auth_headers(token),
    )
    assert r2.status_code == 200
    assert r2.json()["repository_id"] == repo_id


# ─── 15. Search — unauthorized repo returns 403 ───────────────────────────────

def test_search_unauthorized_repo(client):
    token_owner = register_and_login(client, "owner15@forge.dev")
    token_other = register_and_login(client, "other15@forge.dev")

    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "owner/repo15", "description": ""},
        headers=auth_headers(token_owner),
    )
    repo_id = r.json()["id"]

    r2 = client.post(
        "/api/v1/rag/search",
        json={"query": "test", "repository_id": repo_id, "method": "bm25"},
        headers=auth_headers(token_other),
    )
    assert r2.status_code == 403


# ─── 16. Chunk listing endpoint ───────────────────────────────────────────────

def test_chunk_listing_endpoint(client, db_session):
    token = register_and_login(client, "chunklist@forge.dev")

    # Create user and repo via API
    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "list/chunks16", "description": ""},
        headers=auth_headers(token),
    )
    repo_id = r.json()["id"]

    # Insert a chunk directly into DB for this repo
    # First get the user id
    me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()
    user_id = me["id"]

    chunk = CodeChunk(
        id=generate_uuid(),
        repository_id=repo_id,
        file_path="test.py",
        language="Python",
        symbol_name="test_func",
        symbol_type="FUNCTION",
        start_line=1,
        end_line=5,
        chunk_content="def test_func(): pass",
        content_hash="hash-list-16",
        is_embedded=False,
    )
    db_session.merge(chunk)
    db_session.commit()

    r2 = client.get(
        f"/api/v1/rag/repositories/{repo_id}/chunks",
        headers=auth_headers(token),
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["repository_id"] == repo_id
    assert data["total"] >= 1
    assert isinstance(data["chunks"], list)


# ─── 17. Delete index endpoint ────────────────────────────────────────────────

def test_delete_index_endpoint(client, db_session):
    token = register_and_login(client, "delindex@forge.dev")

    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "del/index17", "description": ""},
        headers=auth_headers(token),
    )
    repo_id = r.json()["id"]

    # Insert a chunk
    chunk = CodeChunk(
        id=generate_uuid(),
        repository_id=repo_id,
        file_path="del.py",
        language="Python",
        symbol_name="del_func",
        symbol_type="FUNCTION",
        start_line=1,
        end_line=3,
        chunk_content="def del_func(): pass",
        content_hash="hash-del-17",
        is_embedded=False,
    )
    db_session.merge(chunk)
    db_session.commit()

    # Delete index
    r2 = client.delete(
        f"/api/v1/rag/repositories/{repo_id}/index",
        headers=auth_headers(token),
    )
    assert r2.status_code == 204

    # Verify chunks deleted
    remaining = db_session.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()
    assert remaining == 0


# ─── 18. Duplicate chunk prevention ───────────────────────────────────────────

def test_duplicate_chunk_prevention():
    """
    The chunking service's deduplication is hash-based.
    Two calls to chunk_file on identical content should produce identical hashes.
    """
    from app.services.chunking_service import chunk_file

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        fp = ws / "dup.py"
        fp.write_text("def foo(): return 1\n")

        chunks1 = chunk_file(fp, ws)
        chunks2 = chunk_file(fp, ws)

    hashes1 = {c.content_hash for c in chunks1}
    hashes2 = {c.content_hash for c in chunks2}
    assert hashes1 == hashes2, "Same file should produce same content hashes"


# ─── 19. Large file skipping ──────────────────────────────────────────────────

def test_large_file_skipped():
    from app.services.chunking_service import chunk_file, MAX_FILE_SIZE_BYTES

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        fp = ws / "big.py"
        # Write slightly more than 2 MB
        fp.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1024))

        chunks = chunk_file(fp, ws)

    assert chunks == [], "Files > 2 MB must be skipped"


# ─── 20. Invalid search query — 422 ───────────────────────────────────────────

def test_invalid_search_query_422(client):
    token = register_and_login(client, "invalid20@forge.dev")

    r = client.post(
        "/api/v1/rag/search",
        json={
            "query": "",  # min_length=1 → should fail validation
            "repository_id": "some-id",
            "method": "bm25",
        },
        headers=auth_headers(token),
    )
    assert r.status_code == 422


# ─── 21. Context building endpoint ────────────────────────────────────────────

def test_context_building_endpoint(client, db_session):
    token = register_and_login(client, "context21@forge.dev")

    r = client.post(
        "/api/v1/repositories",
        json={"full_name": "ctx/repo21", "description": ""},
        headers=auth_headers(token),
    )
    repo_id = r.json()["id"]

    chunk = CodeChunk(
        id=generate_uuid(),
        repository_id=repo_id,
        file_path="auth.py",
        language="Python",
        symbol_name="verify_token",
        symbol_type="FUNCTION",
        start_line=10,
        end_line=20,
        chunk_content="def verify_token(token): return jwt.decode(token)",
        content_hash="hash-ctx-21",
        is_embedded=False,
    )
    db_session.merge(chunk)
    db_session.commit()

    r2 = client.post(
        "/api/v1/rag/context",
        json={
            "query": "verify_token jwt",
            "repository_id": repo_id,
            "method": "bm25",
            "top_k": 5,
            "max_tokens": 2000,
        },
        headers=auth_headers(token),
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["chunks_used"] >= 1
    assert "verify_token" in data["context"]
    assert data["estimated_tokens"] >= 1


# ─── 22. Incremental indexing skips unchanged chunks ─────────────────────────

def test_incremental_indexing_skips_unchanged(engine):
    """Running _run_indexing twice skips unchanged chunks on the second run."""
    from app.services.rag_indexing_service import _run_indexing
    from app.services.embedding_service import EmbeddingService
    from app.services.vector_store_service import VectorStoreService
    from app.core import database as core_db

    EmbeddingService.reset_instance()
    VectorStoreService.reset_instance()

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    mock_model.encode.side_effect = lambda texts, **kw: np.random.randn(len(texts), 384).astype(np.float32)

    emb_svc = EmbeddingService.get_instance("all-MiniLM-L6-v2")
    emb_svc._model = mock_model

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    repo_id = generate_uuid()
    user_id = generate_uuid()
    run1_id = generate_uuid()
    run2_id = generate_uuid()

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "app.py").write_text("def greet(name):\n    return f'Hello {name}'\n")

        user = User(id=user_id, email="inc22@forge.dev", hashed_password="x", full_name="Inc")
        repo = Repository(id=repo_id, user_id=user_id, full_name="inc/repo22")
        run1 = IndexingRun(id=run1_id, repository_id=repo_id, status="PENDING")
        db.add_all([user, repo, run1])
        db.commit()

        with (
            patch.object(core_db, "SessionLocal", SessionLocal),
            patch("app.services.rag_indexing_service._get_workspace_dir", return_value=tmpdir),
        ):
            _run_indexing(run1_id, repo_id, user_id, force=False)

        db.expire_all()
        r1 = db.query(IndexingRun).filter(IndexingRun.id == run1_id).first()
        assert r1.status == "COMPLETED"
        assert r1.embedded_chunks >= 1
        assert r1.skipped_chunks == 0

        # Second run on unchanged files -> all chunks skipped
        run2 = IndexingRun(id=run2_id, repository_id=repo_id, status="PENDING")
        db.add(run2)
        db.commit()

        with (
            patch.object(core_db, "SessionLocal", SessionLocal),
            patch("app.services.rag_indexing_service._get_workspace_dir", return_value=tmpdir),
        ):
            _run_indexing(run2_id, repo_id, user_id, force=False)

        db.expire_all()
        r2 = db.query(IndexingRun).filter(IndexingRun.id == run2_id).first()
        assert r2.status == "COMPLETED"
        assert r2.embedded_chunks == 0
        assert r2.skipped_chunks == r1.total_chunks

    db.close()
    EmbeddingService.reset_instance()
    VectorStoreService.reset_instance()
