"""
Database configuration and session management.

Uses SQLite for persistent storage with automatic initialization.
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event  # type: ignore[import-untyped]
from sqlalchemy.ext.declarative import declarative_base  # type: ignore[import-untyped]
from sqlalchemy.orm import Session, sessionmaker  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Database configuration
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR}/manufacturing.db"

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)

# Base class for models
Base = declarative_base()


# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign key support in SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get database session as a context manager.

    Usage:
        from models.database import get_session

        with get_session() as session:
            jobs = session.query(ScheduledJob).all()

    Yields:
        Session: Database session

    Automatically commits on success, rolls back on exception, and closes session.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class DatabaseInitError(RuntimeError):
    """Raised when database table creation fails."""


def init_database() -> bool:
    """
    Initialize database tables.

    Creates all tables if they don't exist.
    Safe to call multiple times.

    Returns:
        True on success.

    Raises:
        DatabaseInitError: If table creation fails.
    """
    try:
        import models.decision_trail  # noqa: F401
        import models.scheduler  # noqa: F401
        import models.workflow  # noqa: F401

        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized: %s", DATABASE_URL)
        logger.info("Database file: %s/manufacturing.db", DATA_DIR)
        return True
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise DatabaseInitError(f"Failed to create tables: {e}") from e


def get_database_info():
    """Get database information for debugging."""
    return {
        "database_url": DATABASE_URL,
        "database_path": str(DATA_DIR / "manufacturing.db"),
        "database_exists": (DATA_DIR / "manufacturing.db").exists(),
        "database_size_mb": (
            round((DATA_DIR / "manufacturing.db").stat().st_size / (1024 * 1024), 2)
            if (DATA_DIR / "manufacturing.db").exists()
            else 0
        ),
    }
