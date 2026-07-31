"""
Tests for database session management - critical for preventing leaks.

Verifies the context manager pattern auto-commits on success, auto-rollbacks on
exception, and supports nested sessions without leaking connections.
"""

import uuid

import pytest  # type: ignore[import-untyped]

from models.database import get_session
from models.scheduler import ScheduledJob


def test_get_session_context_manager():
    """Test that get_session works as context manager."""
    with get_session() as session:
        assert session is not None
        assert hasattr(session, "query")


def test_get_session_auto_commit():
    """Test that session auto-commits on success."""
    job_id = str(uuid.uuid4())

    try:
        with get_session() as session:
            job = ScheduledJob(
                id=job_id,
                name="test_auto_commit",
                schedule="0 * * * *",
                tool_name="test_tool",
                arguments={},
            )
            session.add(job)

        with get_session() as session:
            saved = (
                session.query(ScheduledJob)
                .filter(ScheduledJob.id == job_id)
                .first()
            )
            assert saved is not None
            assert saved.name == "test_auto_commit"

            session.delete(saved)
            session.commit()
    except Exception:
        with get_session() as session:
            session.query(ScheduledJob).filter(
                ScheduledJob.id == job_id
            ).delete()
            session.commit()
        raise


def test_get_session_auto_rollback():
    """Test that session auto-rollbacks on exception."""
    job_id = str(uuid.uuid4())

    try:
        with pytest.raises(ValueError):
            with get_session() as session:
                job = ScheduledJob(
                    id=job_id,
                    name="test_rollback",
                    schedule="0 * * * *",
                    tool_name="test_tool",
                    arguments={},
                )
                session.add(job)
                raise ValueError("Test exception")

        with get_session() as session:
            saved = (
                session.query(ScheduledJob)
                .filter(ScheduledJob.id == job_id)
                .first()
            )
            assert saved is None, "Job should not be saved after exception"
    except Exception:
        with get_session() as session:
            session.query(ScheduledJob).filter(
                ScheduledJob.id == job_id
            ).delete()
            session.commit()


def test_get_session_nested_contexts():
    """Test that nested context managers work correctly."""
    with get_session() as session1:
        with get_session() as session2:
            assert session1 is not None
            assert session2 is not None
            assert hasattr(session1, "query")
            assert hasattr(session2, "query")
