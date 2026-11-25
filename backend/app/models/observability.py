"""
Observability & Evaluation Models — Phase 4 & Phase 8.
Tracks LLM token usage, estimated API costs, latency, and AI evaluation metrics.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Float
from app.core.database import Base
from app.models.user import generate_uuid, get_utc_now


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    session_id = Column(
        String(36),
        ForeignKey("debugging_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_name = Column(String(100), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    status = Column(String(50), default="SUCCESS")  # SUCCESS, UNAVAILABLE, ERROR
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)


class EvaluationMetric(Base):
    __tablename__ = "evaluation_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    session_id = Column(
        String(36),
        ForeignKey("debugging_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    metric_name = Column(String(100), nullable=False, index=True)
    score = Column(Float, nullable=False)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
