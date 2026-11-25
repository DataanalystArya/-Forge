from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import generate_uuid, get_utc_now


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    github_repo_id = Column(String(100), nullable=True)
    full_name = Column(String(255), nullable=False, index=True)  # e.g. "owner/repo"
    description = Column(Text, nullable=True)
    default_branch = Column(String(100), default="main")
    is_private = Column(Boolean, default=False)
    clone_url = Column(String(500), nullable=True)
    status = Column(String(50), default="PENDING")  # PENDING, CLONED, INDEXING, READY, ERROR
    total_files = Column(Integer, default=0)
    total_lines = Column(Integer, default=0)
    languages_json = Column(Text, nullable=True)  # JSON summary of language distribution
    indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    user = relationship("User", back_populates="repositories")
    indexing_jobs = relationship("IndexingJob", back_populates="repository", cascade="all, delete-orphan")
    code_artifacts = relationship("CodeArtifact", back_populates="repository", cascade="all, delete-orphan")
    debugging_sessions = relationship("DebuggingSession", back_populates="repository", cascade="all, delete-orphan")
    security_findings = relationship("SecurityFinding", back_populates="repository", cascade="all, delete-orphan")
    pull_requests = relationship("PullRequest", back_populates="repository", cascade="all, delete-orphan")
    code_chunks = relationship("CodeChunk", back_populates="repository", cascade="all, delete-orphan")
    indexing_runs = relationship("IndexingRun", back_populates="repository", cascade="all, delete-orphan")


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="QUEUED")  # QUEUED, PARSING, EMBEDDING, COMPLETED, FAILED
    indexed_files = Column(Integer, default=0)
    total_files = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    completed_at = Column(DateTime, nullable=True)

    repository = relationship("Repository", back_populates="indexing_jobs")


class CodeArtifact(Base):
    __tablename__ = "code_artifacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False, index=True)
    language = Column(String(50), nullable=True)
    entity_type = Column(String(50), nullable=False)  # FILE, MODULE, CLASS, FUNCTION, METHOD
    entity_name = Column(String(255), nullable=True, index=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    repository = relationship("Repository", back_populates="code_artifacts")
