import os
from sqlalchemy import inspect
from app.core.database import Base, engine, init_db
import app.models  # noqa: F401


def test_database_table_initialization():
    """Verify that all required Phase 1 relational tables exist in metadata and database."""
    init_db()
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    expected_tables = [
        "users",
        "github_accounts",
        "audit_logs",
        "repositories",
        "indexing_jobs",
        "code_artifacts",
        "debugging_sessions",
        "agent_executions",
        "patches",
        "test_executions",
        "security_findings",
        "pull_requests",
    ]

    for expected in expected_tables:
        assert expected in table_names, f"Expected table '{expected}' not found in database schemas"


def test_database_postgres_resilient_fallback(monkeypatch):
    """Verify that when configured with an unreachable PostgreSQL URL, get_engine falls back gracefully to SQLite."""
    from app.core.config import settings
    from app.core.database import get_engine
    
    # Point to an unreachable postgres port
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://fake:fake@127.0.0.1:54399/fake_db")
    
    fallback_engine = get_engine()
    assert fallback_engine.dialect.name == "sqlite", f"Expected sqlite fallback, got {fallback_engine.dialect.name}"
