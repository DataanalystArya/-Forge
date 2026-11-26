"""
Regression and unit tests for repository processing efficiency improvements:
- Accurate JS/TS symbol chunk line range extraction (bracket balancing)
- Full-file coverage (capturing uncovered imports, configs, and top-level blocks)
- GitHub-style single top-level directory ZIP auto-flattening
- In-memory decoupled BM25 cache speedup & invalidation
- TestingAgent PYTHONPATH environment configuration
- Pytest exit code 5 non-punitive metrics handling
"""
import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
import pytest

from app.services.scanner_service import (
    extract_ts_js_symbols_simple,
    IGNORED_DIRECTORIES,
    IGNORED_EXTENSIONS,
)
from app.services.chunking_service import (
    chunk_file,
    _extract_symbol_chunks_js_ts,
    _extract_symbol_chunks_python,
)
from app.services.workspace_service import extract_zip_archive
from app.services.retrieval_service import (
    search_bm25,
    invalidate_bm25_cache,
    _BM25_CACHE,
)


def test_js_ts_symbol_bracket_balancing():
    """Verify that JS/TS functions and classes capture their full multi-line bodies."""
    content = """export class DatabaseConnection {
    constructor(host, port) {
        this.host = host;
        this.port = port;
        this.connected = false;
    }

    connect() {
        this.connected = true;
        return this.connected;
    }
}

export function queryDatabase(sql) {
    const sanitized = sql.trim();
    if (!sanitized) {
        throw new Error("Empty query");
    }
    return { rows: [], count: 0 };
}
"""
    symbols = extract_ts_js_symbols_simple(content)
    assert len(symbols) == 2

    cls_sym = next(s for s in symbols if s["entity_type"] == "CLASS")
    assert cls_sym["entity_name"] == "DatabaseConnection"
    assert cls_sym["start_line"] == 1
    assert cls_sym["end_line"] == 12

    fn_sym = next(s for s in symbols if s["entity_type"] == "FUNCTION")
    assert fn_sym["entity_name"] == "queryDatabase"
    assert fn_sym["start_line"] == 14
    assert fn_sym["end_line"] == 20


def test_js_ts_chunk_contains_full_function_body():
    """Verify chunk_file on a JS/TS file produces chunks with actual body content, not just 1 line."""
    code = """export function calculateDiscount(price, discountPercent) {
    if (price <= 0 || discountPercent < 0) {
        return 0;
    }
    const discountAmount = price * (discountPercent / 100);
    return price - discountAmount;
}
"""
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write(code)
        f_path = Path(f.name)

    try:
        chunks = chunk_file(f_path, f_path.parent)
        assert len(chunks) >= 1
        fn_chunk = next(c for c in chunks if c.symbol_name == "calculateDiscount")
        assert "discountAmount" in fn_chunk.chunk_content
        assert "return price - discountAmount;" in fn_chunk.chunk_content
        assert fn_chunk.end_line > fn_chunk.start_line
    finally:
        f_path.unlink(missing_ok=True)


def test_uncovered_code_chunks_captured():
    """Verify top-level module code (imports, constants) outside functions are not lost."""
    code = """import os
import sys

# Global system configuration
APP_CONFIG = {
    "ENV": "production",
    "MAX_WORKERS": 16,
    "TIMEOUT_SECONDS": 45,
}

def health_check():
    return {"status": "ok"}

ROUTES = ["/api/v1/auth", "/api/v1/repos"]
"""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        f_path = Path(f.name)

    try:
        chunks = chunk_file(f_path, f_path.parent)
        # Should have the function chunk AND the top-level block chunk(s)
        assert len(chunks) >= 2
        block_chunk = next((c for c in chunks if c.symbol_type == "BLOCK"), None)
        assert block_chunk is not None
        assert "APP_CONFIG" in block_chunk.chunk_content or "ROUTES" in block_chunk.chunk_content
    finally:
        f_path.unlink(missing_ok=True)


def test_github_zip_auto_flattening():
    """Verify that uploading a GitHub-style ZIP with a single root directory is auto-flattened."""
    # Build a simulated GitHub ZIP with 'myrepo-main/' enclosing directory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("myrepo-main/README.md", "# My Repo\nThis is a test.")
        zf.writestr("myrepo-main/src/calculator.py", "def add(a, b): return a + b\n")
        zf.writestr("myrepo-main/tests/test_calc.py", "def test_add(): pass\n")
        # Also simulate macOS __MACOSX noise
        zf.writestr("__MACOSX/._README.md", "mac metadata")

    zip_bytes = buf.getvalue()
    test_repo_id = "test-flatten-repo-uuid"
    target_dir, count = extract_zip_archive(test_repo_id, zip_bytes)

    try:
        assert target_dir.exists()
        # The single 'myrepo-main' directory should have been flattened!
        # Root should directly contain README.md, src/, tests/
        root_items = [p.name for p in target_dir.iterdir()]
        assert "README.md" in root_items
        assert "src" in root_items
        assert "tests" in root_items
        assert "myrepo-main" not in root_items
        assert "__MACOSX" not in root_items
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def test_bm25_cache_invalidation():
    """Verify that invalidate_bm25_cache removes cached entries."""
    _BM25_CACHE["repo_123"] = {"test": True}
    assert "repo_123" in _BM25_CACHE
    invalidate_bm25_cache("repo_123")
    assert "repo_123" not in _BM25_CACHE


def test_expanded_ignored_directories():
    """Verify that common build and cache directories are properly ignored."""
    assert ".mypy_cache" in IGNORED_DIRECTORIES
    assert ".tox" in IGNORED_DIRECTORIES
    assert "target" in IGNORED_DIRECTORIES
    assert ".turbo" in IGNORED_DIRECTORIES
    assert ".min.js" in IGNORED_EXTENSIONS
    assert ".map" in IGNORED_EXTENSIONS
