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
