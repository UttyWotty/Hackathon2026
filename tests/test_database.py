"""
Test database functionality and migrations.
"""

from pathlib import Path

from sqlalchemy import text  # type: ignore[import-untyped]


def test_database_file_exists():
    """Test that database file is created."""
    db_path = Path("data/manufacturing.db")
    assert db_path.exists(), "Database file should exist"


def test_database_connection():
    """Test database connection works."""
    from models.database import get_session

    with get_session() as session:
        # Simple query to test connection
        result = session.execute(text("SELECT 1"))
        assert result.fetchone()[0] == 1


def test_migrations_table_exists():
    """Test that migrations tracking table exists."""
    from models.database import get_session

    with get_session() as session:
        result = session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            )
        )
        assert result.fetchone() is not None, "schema_migrations table should exist"


def test_scheduled_jobs_table_has_retry_fields():
    """Test that scheduled_jobs table has new retry fields from migration."""
    from models.database import get_session

    with get_session() as session:
        # Check for retry columns added by migration
        result = session.execute(text("PRAGMA table_info(scheduled_jobs)"))
        columns = {row[1] for row in result.fetchall()}

        assert "max_retries" in columns, "max_retries column should exist"
        assert "retry_count" in columns, "retry_count column should exist"
        assert "retry_backoff" in columns, "retry_backoff column should exist"


def test_all_required_tables_exist():
    """Test that all required tables exist."""
    from models.database import get_session

    required_tables = [
        "scheduled_jobs",
        "audit_logs",
        "metrics",  # Note: actual table name is 'metrics', not 'system_metrics'
        "alert_rules",
        "alert_history",
        "schema_migrations",
    ]

    with get_session() as session:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        existing_tables = {row[0] for row in result.fetchall()}

        for table in required_tables:
            assert table in existing_tables, f"Table {table} should exist"
