"""
Pydantic schemas for Phase 3 — Code RAG endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

class IndexRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="If true, delete existing chunks and re-embed from scratch.",
    )


class IndexStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    repository_id: str
    status: str
    total_files: int
    processed_files: int
    total_chunks: int
    embedded_chunks: int
    skipped_chunks: int
    error_message: Optional[str]
    embedding_model: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    # Extra info
    vector_mode: Optional[str] = None  # "server" or "memory"
    qdrant_available: Optional[bool] = None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language or symbol query.",
    )
    repository_id: str = Field(..., description="Repository to search within.")
    method: Literal["semantic", "bm25", "hybrid"] = Field(
        default="hybrid",
        description="Retrieval method to use.",
    )
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResultItem(BaseModel):
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
    retrieval_method: str


class SearchResponse(BaseModel):
    query: str
    method: str
    results: List[SearchResultItem]
    total: int
    latency_ms: float
    qdrant_available: bool
    vector_mode: str  # "server" | "memory" | "unavailable"


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

class ContextRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    repository_id: str
    top_k: int = Field(default=5, ge=1, le=20)
    method: Literal["semantic", "bm25", "hybrid"] = "hybrid"
    max_tokens: int = Field(
        default=4000,
        description="Approximate token budget for the assembled context.",
    )


class ContextResponse(BaseModel):
    query: str
    context: str
    chunks_used: int
    estimated_tokens: int


# ---------------------------------------------------------------------------
# Chunk listing
# ---------------------------------------------------------------------------

class ChunkItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_path: str
    language: Optional[str]
    symbol_name: Optional[str]
    symbol_type: str
    start_line: int
    end_line: int
    content_hash: str
    is_embedded: bool
    embedding_model: Optional[str]
    created_at: datetime


class ChunkListResponse(BaseModel):
    repository_id: str
    total: int
    page: int
    page_size: int
    chunks: List[ChunkItem]
