"""
RAG (Retrieval-Augmented Generation) database models.
Phase 3 — Code Intelligence layer.
"""
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey,
    Text, Integer, Float, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import generate_uuid, get_utc_now


class CodeChunk(Base):
    """
    A single indexable unit of source code, produced by the chunking pipeline.

    Each chunk represents a function, class, or logical sliding-window block
    from a repository file.  Chunk content is stored in the DB (for BM25) and
    also embedded into Qdrant (for semantic search).
    """
    __tablename__ = "code_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    repository_id = Column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path = Column(String(1000), nullable=False, index=True)
    language = Column(String(50), nullable=True)

    # Symbol metadata (None for sliding-window chunks)
    symbol_name = Column(String(255), nullable=True, index=True)
    # FUNCTION | CLASS | METHOD | BLOCK | FILE
    symbol_type = Column(String(50), nullable=False, default="BLOCK")

    start_line = Column(Integer, nullable=False, default=1)
    end_line = Column(Integer, nullable=False, default=1)

    # Full chunk text — stored for BM25 and snippet rendering
    chunk_content = Column(Text, nullable=False)
    # SHA-256 of chunk_content — used for incremental re-indexing
    content_hash = Column(String(64), nullable=False, index=True)

    # Embedding tracking
    embedding_model = Column(String(100), nullable=True)
    is_embedded = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    repository = relationship("Repository", back_populates="code_chunks")

    __table_args__ = (
        # Prevents duplicate chunks for the same symbol in the same file
        UniqueConstraint(
            "repository_id", "file_path", "symbol_name", "start_line",
            name="uq_chunk_repo_file_symbol_line",
        ),
        Index("ix_code_chunks_repo_file", "repository_id", "file_path"),
    )


class IndexingRun(Base):
    """
    Tracks a Phase-3 RAG indexing run for a repository.

    One IndexingRun is created each time the user triggers embedding for a repo.
    It is separate from IndexingJob (Phase 2) which tracked structural scanning.
    """
    __tablename__ = "indexing_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    repository_id = Column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # PENDING | RUNNING | COMPLETED | FAILED
    status = Column(String(50), nullable=False, default="PENDING")

    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    embedded_chunks = Column(Integer, default=0)
    skipped_chunks = Column(Integer, default=0)  # unchanged on re-index

    error_message = Column(Text, nullable=True)
    embedding_model = Column(String(100), nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    repository = relationship("Repository", back_populates="indexing_runs")


class RetrievalLog(Base):
    """
    Audit log for Code RAG search queries.
    Records what was searched, by whom, and how fast results came back.
    """
    __tablename__ = "retrieval_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id = Column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    query_text = Column(Text, nullable=False)
    results_count = Column(Integer, default=0)
    # semantic | bm25 | hybrid
    retrieval_method = Column(String(50), nullable=True)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    user = relationship("User")
