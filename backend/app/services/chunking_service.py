"""
Chunking Service — Phase 3 Code RAG.

Converts source files into indexable CodeChunk records.

Strategy:
1. For Python files: use Tree-sitter (preferred) or Python AST to extract
   function/class bodies as individual chunks.
2. For JS/TS files: use the existing regex-based symbol extractor from
   scanner_service.
3. For all other text files: sliding-window chunks (max RAG_CHUNK_MAX_LINES
   lines, RAG_CHUNK_OVERLAP_LINES overlap).
4. Files larger than 2 MB are skipped (same threshold as scanner_service).
5. Deduplication via content_hash — identical content = same hash → skipped.

Returns List[ChunkData] — pure data, no DB writes.  The indexing service
calls the DB and Qdrant.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.services.scanner_service import (
    IGNORED_DIRECTORIES,
    IGNORED_EXTENSIONS,
    LANGUAGE_MAP,
    is_binary_file,
    extract_python_symbols_ast,
    extract_ts_js_symbols_simple,
)

logger = logging.getLogger("forge.chunking")

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

# Try tree-sitter python for chunking (same approach as scanner_service)
_TS_PYTHON_PARSER = None
try:
    from tree_sitter import Language, Parser
    import tree_sitter_python

    _PY_LANGUAGE = Language(tree_sitter_python.language())
    _TS_PYTHON_PARSER = Parser(_PY_LANGUAGE)
except Exception:
    pass


@dataclass
class ChunkData:
    """A single code chunk ready for embedding and storage."""
    file_path: str           # relative to repository workspace root
    language: Optional[str]
    symbol_name: Optional[str]
    symbol_type: str         # FUNCTION | CLASS | BLOCK | FILE
    start_line: int
    end_line: int
    chunk_content: str
    content_hash: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lines(content: str) -> List[str]:
    return content.splitlines()


def _sliding_window_chunks(
    lines: List[str],
    rel_path: str,
    language: Optional[str],
    max_lines: int,
    overlap: int,
    max_chunks: int,
) -> List[ChunkData]:
    """Split a file into overlapping window chunks."""
    chunks: List[ChunkData] = []
    total = len(lines)
    if total == 0:
        return chunks

    step = max(1, max_lines - overlap)
    chunk_idx = 0
    start = 0
    while start < total and chunk_idx < max_chunks:
        end = min(start + max_lines, total)
        content = "\n".join(lines[start:end])
        chunks.append(
            ChunkData(
                file_path=rel_path,
                language=language,
                symbol_name=None,
                symbol_type="BLOCK",
                start_line=start + 1,
                end_line=end,
                chunk_content=content,
                content_hash=_hash(content),
            )
        )
        start += step
        chunk_idx += 1

    return chunks


def _collect_uncovered_chunks(
    file_lines: List[str],
    covered_ranges: List[Tuple[int, int]],
    rel_path: str,
    language: str,
    max_lines: int,
    overlap: int,
    max_chunks: int,
) -> List[ChunkData]:
    """Capture code outside function/class definitions (imports, configs, script code)."""
    if max_chunks <= 0:
        return []

    total_lines = len(file_lines)
    if total_lines == 0:
        return []

    # Sort and merge covered ranges
    sorted_ranges = sorted(covered_ranges, key=lambda r: r[0])
    uncovered_spans: List[Tuple[int, int]] = []
    curr = 1

    for start, end in sorted_ranges:
        if start > curr:
            uncovered_spans.append((curr, start - 1))
        curr = max(curr, end + 1)
    if curr <= total_lines:
        uncovered_spans.append((curr, total_lines))

    chunks: List[ChunkData] = []
    for u_start, u_end in uncovered_spans:
        if len(chunks) >= max_chunks:
            break
        span_lines = file_lines[u_start - 1 : u_end]
        # Ignore empty or comment-only whitespace spans
        non_empty = [l for l in span_lines if l.strip() and not l.strip().startswith("#")]
        if not non_empty:
            continue

        if len(span_lines) <= max_lines:
            body = "\n".join(span_lines)
            chunks.append(
                ChunkData(
                    file_path=rel_path,
                    language=language,
                    symbol_name=None,
                    symbol_type="BLOCK",
                    start_line=u_start,
                    end_line=u_end,
                    chunk_content=body,
                    content_hash=_hash(body),
                )
            )
        else:
            sub = _sliding_window_chunks(
                span_lines, rel_path, language, max_lines, overlap, max_chunks - len(chunks)
            )
            for sc in sub:
                sc.start_line += u_start - 1
                sc.end_line += u_start - 1
            chunks.extend(sub)

    return chunks


def _extract_symbol_chunks_python(
    content: str,
    rel_path: str,
    language: str,
    max_lines: int,
    overlap: int,
    max_chunks: int,
) -> List[ChunkData]:
    """Extract Python function/class chunks, splitting large ones with overlap, and capturing module code."""
    # Prefer tree-sitter; fall back to AST
    if _TS_PYTHON_PARSER:
        try:
            from app.services.scanner_service import extract_python_symbols_treesitter
            symbols = extract_python_symbols_treesitter(content.encode("utf-8"))
        except Exception:
            symbols = extract_python_symbols_ast(content, rel_path)
    else:
        symbols = extract_python_symbols_ast(content, rel_path)

    file_lines = _lines(content)
    chunks: List[ChunkData] = []
    covered_ranges: List[Tuple[int, int]] = []

    for sym in symbols:
        if len(chunks) >= max_chunks:
            break
        s_start = sym["start_line"] - 1  # 0-indexed
        s_end = sym["end_line"]           # exclusive
        sym_lines = file_lines[s_start:s_end]
        sym_len = len(sym_lines)
        covered_ranges.append((sym["start_line"], sym["end_line"]))

        if sym_len <= max_lines:
            body = "\n".join(sym_lines)
            chunks.append(
                ChunkData(
                    file_path=rel_path,
                    language=language,
                    symbol_name=sym["entity_name"],
                    symbol_type=sym["entity_type"],
                    start_line=sym["start_line"],
                    end_line=sym["end_line"],
                    chunk_content=body,
                    content_hash=_hash(body),
                )
            )
        else:
            # Large symbol — split with overlap
            sub_chunks = _sliding_window_chunks(
                sym_lines, rel_path, language, max_lines, overlap,
                max_chunks - len(chunks),
            )
            # Adjust line numbers relative to file
            for sc in sub_chunks:
                sc.symbol_name = sym["entity_name"]
                sc.symbol_type = sym["entity_type"]
                sc.start_line += s_start
                sc.end_line += s_start
            chunks.extend(sub_chunks)

    # Capture top-level module code (imports, constants, global logic) outside symbols
    if len(chunks) < max_chunks:
        uncovered = _collect_uncovered_chunks(
            file_lines, covered_ranges, rel_path, language, max_lines, overlap, max_chunks - len(chunks)
        )
        chunks.extend(uncovered)

    # If no symbols extracted at all, fall back to sliding window
    if not chunks:
        chunks = _sliding_window_chunks(
            file_lines, rel_path, language, max_lines, overlap, max_chunks
        )

    # Sort chunks in file order by start_line
    return sorted(chunks, key=lambda c: c.start_line)


def _extract_symbol_chunks_js_ts(
    content: str,
    rel_path: str,
    language: str,
    max_lines: int,
    overlap: int,
    max_chunks: int,
) -> List[ChunkData]:
    """Extract JS/TS function/class chunks, splitting large ones and capturing module code."""
    symbols = extract_ts_js_symbols_simple(content)
    file_lines = _lines(content)
    chunks: List[ChunkData] = []
    covered_ranges: List[Tuple[int, int]] = []

    for sym in symbols:
        if len(chunks) >= max_chunks:
            break
        s_start = sym["start_line"] - 1
        s_end = sym["end_line"]
        sym_lines = file_lines[s_start:s_end]
        sym_len = len(sym_lines)
        covered_ranges.append((sym["start_line"], sym["end_line"]))

        if sym_len <= max_lines:
            body = "\n".join(sym_lines)
            chunks.append(
                ChunkData(
                    file_path=rel_path,
                    language=language,
                    symbol_name=sym["entity_name"],
                    symbol_type=sym["entity_type"],
                    start_line=sym["start_line"],
                    end_line=sym["end_line"],
                    chunk_content=body,
                    content_hash=_hash(body),
                )
            )
        else:
            sub_chunks = _sliding_window_chunks(
                sym_lines, rel_path, language, max_lines, overlap,
                max_chunks - len(chunks),
            )
            for sc in sub_chunks:
                sc.symbol_name = sym["entity_name"]
                sc.symbol_type = sym["entity_type"]
                sc.start_line += s_start
                sc.end_line += s_start
            chunks.extend(sub_chunks)

    # Capture top-level code (imports, exports, configurations) outside symbols
    if len(chunks) < max_chunks:
        uncovered = _collect_uncovered_chunks(
            file_lines, covered_ranges, rel_path, language, max_lines, overlap, max_chunks - len(chunks)
        )
        chunks.extend(uncovered)

    if not chunks:
        chunks = _sliding_window_chunks(
            file_lines, rel_path, language, max_lines, overlap, max_chunks
        )
    return sorted(chunks, key=lambda c: c.start_line)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_file(
    file_path: Path,
    workspace_root: Path,
    max_lines: int = 80,
    overlap: int = 10,
    max_chunks: int = 500,
) -> List[ChunkData]:
    """
    Produce a list of ChunkData objects for a single source file.

    Args:
        file_path: Absolute path to the file.
        workspace_root: Root of the repository workspace (for relative path).
        max_lines: Maximum lines per chunk (sliding window).
        overlap: Overlap lines between consecutive window chunks.
        max_chunks: Hard cap on chunks per file.

    Returns:
        List of ChunkData.  Empty list when the file should be skipped.
    """
    try:
        stat = file_path.stat()
        if stat.st_size > MAX_FILE_SIZE_BYTES:
            logger.debug(f"Skipping large file: {file_path} ({stat.st_size} bytes)")
            return []
    except Exception:
        return []

    ext = file_path.suffix.lower()
    if ext in IGNORED_EXTENSIONS:
        return []
    if is_binary_file(file_path):
        return []

    try:
        rel_path = str(file_path.relative_to(workspace_root))
    except ValueError:
        rel_path = str(file_path)

    language = LANGUAGE_MAP.get(ext)

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    if not content.strip():
        return []

    if language == "Python":
        return _extract_symbol_chunks_python(
            content, rel_path, language, max_lines, overlap, max_chunks
        )
    elif language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
        return _extract_symbol_chunks_js_ts(
            content, rel_path, language, max_lines, overlap, max_chunks
        )
    else:
        # Sliding window for all other text formats
        return _sliding_window_chunks(
            _lines(content), rel_path, language, max_lines, overlap, max_chunks
        )


def chunk_repository(
    workspace_dir: str,
    max_lines: int = 80,
    overlap: int = 10,
    max_chunks_per_file: int = 500,
) -> List[ChunkData]:
    """
    Walk the entire repository workspace and produce chunks for all files.

    Respects the same IGNORED_DIRECTORIES and IGNORED_EXTENSIONS as the
    Phase-2 scanner.
    """
    workspace = Path(workspace_dir)
    all_chunks: List[ChunkData] = []

    for root, dirs, files in os.walk(workspace):
        # Prune ignored dirs in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

        for filename in files:
            fp = Path(root) / filename
            chunks = chunk_file(
                fp, workspace, max_lines, overlap, max_chunks_per_file
            )
            all_chunks.extend(chunks)

    logger.info(
        f"Chunked repository at '{workspace_dir}': {len(all_chunks)} total chunks."
    )
    return all_chunks
