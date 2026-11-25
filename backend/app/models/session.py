from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import generate_uuid, get_utc_now


class DebuggingSession(Base):
    __tablename__ = "debugging_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    error_logs = Column(Text, nullable=True)
    status = Column(String(50), default="CREATED")  # CREATED, PLANNING, ANALYZING, CODING, TESTING, REPAIRING, REVIEWING, COMPLETED, FAILED
    current_phase = Column(String(100), default="PLANNING")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    repository = relationship("Repository", back_populates="debugging_sessions")
    user = relationship("User", back_populates="debugging_sessions")
    agent_executions = relationship("AgentExecution", back_populates="session", cascade="all, delete-orphan")
    patches = relationship("Patch", back_populates="session", cascade="all, delete-orphan")
    test_executions = relationship("TestExecution", back_populates="session", cascade="all, delete-orphan")
    security_findings = relationship("SecurityFinding", back_populates="session", cascade="all, delete-orphan")
    pull_requests = relationship("PullRequest", back_populates="session", cascade="all, delete-orphan")


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("debugging_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False, index=True)
    input_state_json = Column(Text, nullable=True)
    output_state_json = Column(Text, nullable=True)
    duration_ms = Column(Integer, default=0)
    status = Column(String(50), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    session = relationship("DebuggingSession", back_populates="agent_executions")


class Patch(Base):
    __tablename__ = "patches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("debugging_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    iteration = Column(Integer, default=1)
    diff_content = Column(Text, nullable=False)
    affected_files_json = Column(Text, nullable=True)
    rationale = Column(Text, nullable=True)
    is_applied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_utc_now)

    session = relationship("DebuggingSession", back_populates="patches")
    test_executions = relationship("TestExecution", back_populates="patch", cascade="all, delete-orphan")


class TestExecution(Base):
    __tablename__ = "test_executions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("debugging_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    patch_id = Column(String(36), ForeignKey("patches.id", ondelete="SET NULL"), nullable=True)
    command = Column(Text, nullable=True)
    exit_code = Column(Integer, default=0)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    passed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)

    session = relationship("DebuggingSession", back_populates="test_executions")
    patch = relationship("Patch", back_populates="test_executions")


class SecurityFinding(Base):
    __tablename__ = "security_findings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("debugging_sessions.id", ondelete="SET NULL"), nullable=True)
    rule_id = Column(String(150), nullable=False)
    severity = Column(String(50), default="MEDIUM")  # LOW, MEDIUM, HIGH, CRITICAL
    file_path = Column(String(1000), nullable=False)
    line_number = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    repository = relationship("Repository", back_populates="security_findings")
    session = relationship("DebuggingSession", back_populates="security_findings")


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("debugging_sessions.id", ondelete="CASCADE"), nullable=False)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    branch_name = Column(String(255), nullable=False)
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String(500), nullable=True)
    title = Column(String(255), nullable=False)
    status = Column(String(50), default="PROPOSED")  # PROPOSED, APPROVED, CREATED, MERGED, CLOSED
    created_at = Column(DateTime, default=get_utc_now)

    session = relationship("DebuggingSession", back_populates="pull_requests")
    repository = relationship("Repository", back_populates="pull_requests")
