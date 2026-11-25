"""
Retrieval Service — Phase 3 Code RAG.

Implements:
- BM25 keyword search (over DB-stored chunk content)
- Semantic vector search (via Qdrant)
- Hybrid search with Reciprocal Rank Fusion (RRF)
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("forge.retrieval")


def _tokenize(text: str) -> list:
    """
    Code-aware tokenizer: lowercase + split on whitespace AND common code
    punctuation (parens, brackets, braces, commas, colons, dots, underscores
    treated as word boundaries for sub-word matching).
    """
    # Split on any non-alphanumeric character, keep only non-empty tokens ≥ 2 chars
    tokens = re.findall(r"[a-z0-9_]{2,}", text.lower())
    # Also emit sub-tokens for snake_case / camelCase identifiers
    expanded = []
    for tok in tokens:
        expanded.append(tok)
        # snake_case split
        parts = tok.split("_")
        if len(parts) > 1:
            expanded.extend(p for p in parts if len(p) >= 2)
    return expanded


@dataclass
class SearchResult:
    """Unified search result returned by all retrieval methods."""
    chunk_id: str
    repository_id: str
    file_path: str
    symbol_name: Optional[str]
    symbol_type: str
    start_line: int
    end_line: int
    language: Optional[str]
    chunk_content: str
    score: float
    retrieval_method: str  # semantic | bm25 | hybrid


# ---------------------------------------------------------------------------
# BM25 Search
# ---------------------------------------------------------------------------

def search_bm25(
    query: str,
    repository_id: str,
    db: Session,
    top_k: int = 10,
) -> List[SearchResult]:
    """
    Build a BM25 index on-the-fly from code_chunks in the DB for the given
    repository and return the top-k results.

    Uses rank-bm25 (BM25Okapi).  Returns [] when no chunks are indexed.
    """
    try:
        from rank_bm25 import BM25Plus  # type: ignore
        from app.models.rag import CodeChunk

        # Fetch all chunks for this repository
        chunks = (
            db.query(CodeChunk)
            .filter(CodeChunk.repository_id == repository_id)
            .all()
        )
        if not chunks:
            return []

        # Tokenise — code-aware: splits on punctuation to handle identifiers
        corpus_tokens = [_tokenize(chunk.chunk_content) for chunk in chunks]
        bm25 = BM25Plus(corpus_tokens)

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        query_set = set(query_tokens)
        scores = bm25.get_scores(query_tokens)

        # Build indexed list sorted by score descending
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        results = []
        for idx, score in ranked:
            if score <= 0:
                continue
            # Ensure at least one query token actually appears in the chunk
            # (BM25Plus adds a positive delta even when tf == 0)
            if not any(tok in query_set for tok in corpus_tokens[idx]):
                continue
            chunk = chunks[idx]
            results.append(
                SearchResult(
                    chunk_id=chunk.id,
                    repository_id=chunk.repository_id,
                    file_path=chunk.file_path,
                    symbol_name=chunk.symbol_name,
                    symbol_type=chunk.symbol_type,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    language=chunk.language,
                    chunk_content=chunk.chunk_content,
                    score=float(score),
                    retrieval_method="bm25",
                )
            )
        return results

    except Exception as exc:
        logger.error(f"BM25 search failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------

def search_semantic(
    query: str,
    repository_id: str,
    top_k: int = 10,
) -> List[SearchResult]:
    """
    Encode query with EmbeddingService and search Qdrant.
    Returns [] when embedding or Qdrant is unavailable.
    """
    try:
        from app.services.embedding_service import EmbeddingService, EmbeddingUnavailableError
        from app.services.vector_store_service import VectorStoreService

        emb_svc = EmbeddingService.get_instance()
        vec_svc = VectorStoreService.get_instance()

        query_vector = emb_svc.encode_single(query)
        hits = vec_svc.search_semantic(query_vector, repository_id, top_k)

        return [
            SearchResult(
                chunk_id=h.chunk_id,
                repository_id=h.repository_id,
                file_path=h.file_path,
                symbol_name=h.symbol_name,
                symbol_type=h.symbol_type,
                start_line=h.start_line,
                end_line=h.end_line,
                language=h.language,
                chunk_content=h.chunk_content,
                score=h.score,
                retrieval_method="semantic",
            )
            for h in hits
        ]
    except Exception as exc:
        logger.error(f"Semantic search failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Hybrid Search (RRF)
# ---------------------------------------------------------------------------

def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score for a given rank (0-indexed)."""
    return 1.0 / (k + rank + 1)


def search_hybrid(
    query: str,
    repository_id: str,
    db: Session,
    top_k: int = 10,
    semantic_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> List[SearchResult]:
    """
    Merge semantic and BM25 results with Reciprocal Rank Fusion.

    Falls back to whichever source is available if one is unavailable.
    """
    sem_results = search_semantic(query, repository_id, top_k=top_k * 2)
    bm25_results = search_bm25(query, repository_id, db, top_k=top_k * 2)

    # If only one source available, return it directly
    if not sem_results:
        for r in bm25_results[:top_k]:
            r.retrieval_method = "hybrid"
        return bm25_results[:top_k]
    if not bm25_results:
        for r in sem_results[:top_k]:
            r.retrieval_method = "hybrid"
        return sem_results[:top_k]

    # Build RRF score table keyed by chunk_id
    scores: dict[str, float] = {}
    result_map: dict[str, SearchResult] = {}

    for rank, res in enumerate(sem_results):
        scores[res.chunk_id] = scores.get(res.chunk_id, 0) + semantic_weight * _rrf_score(rank)
        result_map[res.chunk_id] = res

    for rank, res in enumerate(bm25_results):
        scores[res.chunk_id] = scores.get(res.chunk_id, 0) + bm25_weight * _rrf_score(rank)
        if res.chunk_id not in result_map:
            result_map[res.chunk_id] = res

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    output = []
    for chunk_id, fused_score in ranked:
        res = result_map[chunk_id]
        output.append(
            SearchResult(
                chunk_id=res.chunk_id,
                repository_id=res.repository_id,
                file_path=res.file_path,
                symbol_name=res.symbol_name,
                symbol_type=res.symbol_type,
                start_line=res.start_line,
                end_line=res.end_line,
                language=res.language,
                chunk_content=res.chunk_content,
                score=fused_score,
                retrieval_method="hybrid",
            )
        )
    return output
