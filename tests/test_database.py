"""
Test database functionality and migrations.
"""

from pathlib import Path

from sqlalchemy import text  # type: ignore[import-untyped]


def test_database_file_exists():
    """The SQLite file is created on first use, at the module's own DATA_DIR.

    The path is taken from models.database rather than assumed relative to the
    working directory: the database lives under src/backend/data, so a
    hardcoded "data/manufacturing.db" only resolves when pytest happens to run
    from that directory. It is also created lazily, so a session is opened
    first rather than assuming a previous test made the file.
    """
    from models.database import DATA_DIR, get_session

    with get_session():
        pass

    db_path = Path(DATA_DIR) / "manufacturing.db"
    assert db_path.exists(), f"Database file should exist at {db_path}"


def test_database_connection():
    """Test database connection works."""
    from models.database import get_session

    with get_session() as session:
        # Simple query to test connection
        result = session.execute(text("SELECT 1"))
        assert result.fetchone()[0] == 1


def test_migrations_table_exists():
    """Test that core tables exist after init_database."""
    from models.database import get_session

    with get_session() as session:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        existing_tables = {row[0] for row in result.fetchall()}
        assert "scheduled_jobs" in existing_tables, "scheduled_jobs table should exist"


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
        "job_execution_history",
        "decision_runs",
        "decision_steps",
        "notes",
        "projects",
        "tasks",
        "task_timers",
    ]

    with get_session() as session:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        existing_tables = {row[0] for row in result.fetchall()}

        for table in required_tables:
            assert table in existing_tables, f"Table {table} should exist"
