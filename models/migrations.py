"""
Database Schema Migrations - Auto-apply on startup.

This module ensures the database schema stays in sync with the models.
Migrations run automatically when the server starts.

Author: Utku Gulbardak
Date: 2025-11-24
"""

import logging
from typing import List, Tuple

from sqlalchemy import text  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Full-text search schema for notes and documents. These SQLite FTS5 virtual
# tables and their sync triggers are kept out of the versioned migration list
# because trigger bodies contain semicolons that the split-on-";" migration
# runner cannot handle; each statement is instead executed individually here.
# All statements use IF NOT EXISTS so the setup is idempotent.
SEARCH_INDEX_STATEMENTS: Tuple[str, ...] = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts "
    "USING fts5(note_id, title, content)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts "
    "USING fts5(doc_id, filename, content)",
    """
    CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
        INSERT INTO notes_fts(note_id, title, content)
        VALUES (new.id, new.title, COALESCE(new.content, ''));
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
        DELETE FROM notes_fts WHERE note_id = old.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
        DELETE FROM notes_fts WHERE note_id = old.id;
        INSERT INTO notes_fts(note_id, title, content)
        VALUES (new.id, new.title, COALESCE(new.content, ''));
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
        INSERT INTO documents_fts(doc_id, filename, content)
        VALUES (new.id, new.filename, COALESCE(new.extracted_text, ''));
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
        DELETE FROM documents_fts WHERE doc_id = old.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
        DELETE FROM documents_fts WHERE doc_id = old.id;
        INSERT INTO documents_fts(doc_id, filename, content)
        VALUES (new.id, new.filename, COALESCE(new.extracted_text, ''));
    END
    """,
)


def ensure_search_indexes(session: Session) -> bool:
    """
    Create the FTS5 search tables and sync triggers if they do not exist.

    Runs on startup and in tests so keyword search works on a fresh database
    instead of failing with "no such table: notes_fts". Idempotent.

    Args:
        session: Database session.

    Returns:
        True if the search schema is present after the call, False on error.
    """
    try:
        for statement in SEARCH_INDEX_STATEMENTS:
            session.execute(text(statement))
        session.commit()
        logger.info("✅ Full-text search schema ensured (notes_fts, documents_fts)")
        return True
    except Exception as e:  # noqa: BLE001 - startup must not crash on FTS setup
        logger.error("❌ Failed to ensure search indexes: %s", e)
        session.rollback()
        return False


def get_current_schema_version(session: Session) -> int:
    """
    Get current database schema version.

    Returns:
        Current version number (0 if no version table exists)
    """
    try:
        result = session.execute(
            text("SELECT MAX(version) FROM schema_migrations")
        ).fetchone()
        return result[0] if result and result[0] else 0
    except Exception:
        # Table doesn't exist yet
        return 0


def create_migrations_table(session: Session):
    """Create schema_migrations tracking table."""
    try:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """))
        session.commit()
        logger.info("✅ Schema migrations table created")
    except Exception as e:
        logger.error(f"Error creating migrations table: {e}")
        session.rollback()


def record_migration(session: Session, version: int, description: str):
    """Record that a migration has been applied."""
    session.execute(
        text(
            "INSERT INTO schema_migrations (version, description) VALUES (:version, :description)"
        ),
        {"version": version, "description": description},
    )
    session.commit()


def get_migrations() -> List[Tuple[int, str, str]]:
    """
    Define all database migrations.

    Returns:
        List of tuples: (version, description, sql)
    """
    return [
        (
            1,
            "Add retry fields to scheduled_jobs",
            """
            ALTER TABLE scheduled_jobs ADD COLUMN max_retries INTEGER DEFAULT 3;
            ALTER TABLE scheduled_jobs ADD COLUMN retry_count INTEGER DEFAULT 0;
            ALTER TABLE scheduled_jobs ADD COLUMN retry_backoff REAL DEFAULT 1.5;
            """,
        ),
        # Add future migrations here with incrementing version numbers
        # (2, "Add new feature", "ALTER TABLE ..."),
    ]


def apply_migration(session: Session, version: int, description: str, sql: str) -> bool:
    """
    Apply a single migration.

    Args:
        session: Database session
        version: Migration version number
        description: Migration description
        sql: SQL statements to execute

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📦 Applying migration {version}: {description}")

        # Split SQL by semicolon and execute each statement
        statements = [s.strip() for s in sql.split(";") if s.strip()]

        for statement in statements:
            try:
                session.execute(text(statement))
            except Exception as e:
                # If column already exists, that's fine (idempotent)
                if (
                    "duplicate column" in str(e).lower()
                    or "already exists" in str(e).lower()
                ):
                    logger.debug(f"Column already exists, skipping: {e}")
                else:
                    raise

        # Record migration
        record_migration(session, version, description)

        logger.info(f"✅ Migration {version} applied successfully")
        return True

    except Exception as e:
        logger.error(f"❌ Migration {version} failed: {e}")
        session.rollback()
        return False


def run_migrations(session: Session) -> bool:
    """
    Run all pending migrations.

    Args:
        session: Database session

    Returns:
        True if all migrations succeeded, False otherwise
    """
    try:
        # Ensure migrations table exists
        create_migrations_table(session)

        # Get current version
        current_version = get_current_schema_version(session)

        # Get all migrations
        migrations = get_migrations()

        # Filter to only pending migrations
        pending = [m for m in migrations if m[0] > current_version]

        if not pending:
            logger.info(f"✅ Database schema up to date (version {current_version})")
            return True

        logger.info(f"📦 Found {len(pending)} pending migration(s)")

        # Apply each pending migration
        success = True
        for version, description, sql in pending:
            if not apply_migration(session, version, description, sql):
                success = False
                break

        if success:
            new_version = get_current_schema_version(session)
            logger.info(
                f"✅ All migrations applied successfully (version {current_version} → {new_version})"
            )
        else:
            logger.warning("⚠️  Some migrations failed - check logs")

        return success

    except Exception as e:
        logger.error(f"❌ Migration system error: {e}")
        return False


def check_and_migrate(session: Session):
    """
    Check database schema and apply migrations if needed.

    This is the main entry point called during server startup.

    Args:
        session: Database session
    """
    logger.info("🔍 Checking database schema...")

    try:
        success = run_migrations(session)
        # Search tables live outside the versioned migration list; ensure them
        # every startup so a fresh database has working keyword search.
        search_ok = ensure_search_indexes(session)

        if success and search_ok:
            logger.info("✅ Database schema check complete")
        else:
            logger.warning("⚠️  Database schema check completed with warnings")

    except Exception as e:
        logger.error(f"❌ Database schema check failed: {e}")
