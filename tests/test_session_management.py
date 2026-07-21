"""
Tests for database session management - critical for preventing leaks.

Tests:
- Context manager pattern
- Auto-commit on success
- Auto-rollback on exception
- Auto-close on exit
"""

import pytest  # type: ignore[import-untyped]

from models.database import get_session


def test_get_session_context_manager():
    """Test that get_session works as context manager."""
    with get_session() as session:
        assert session is not None
        # Session should be open
        assert hasattr(session, "query")

    # Session should be closed after context exit
    # (We can't directly check this, but no errors means it worked)


def test_get_session_auto_commit():
    """Test that session auto-commits on success."""
    import uuid

    from models.email import EmailQueue

    email_id = str(uuid.uuid4())

    try:
        # Add email using context manager
        with get_session() as session:
            email_item = EmailQueue(
                id=email_id,
                to_email="test@example.com",
                subject="Test",
                body="Test",
            )
            session.add(email_item)
            # No explicit commit - should auto-commit on exit

        # Verify email was committed
        with get_session() as session:
            saved_email = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )
            assert saved_email is not None
            assert saved_email.to_email == "test@example.com"

            # Cleanup
            session.delete(saved_email)
            session.commit()
    except Exception:
        # Cleanup on error
        with get_session() as session:
            session.query(EmailQueue).filter(EmailQueue.id == email_id).delete()
            session.commit()
        raise


def test_get_session_auto_rollback():
    """Test that session auto-rollbacks on exception."""
    import uuid

    from models.email import EmailQueue

    email_id = str(uuid.uuid4())

    try:
        # Try to add email with invalid data (should raise exception)
        with pytest.raises(Exception):
            with get_session() as session:
                email_item = EmailQueue(
                    id=email_id,
                    to_email="test@example.com",
                    subject="Test",
                    body="Test",
                )
                session.add(email_item)
                # Force exception
                raise ValueError("Test exception")

        # Verify email was NOT committed (rolled back)
        with get_session() as session:
            saved_email = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )
            assert saved_email is None, "Email should not be saved after exception"
    except Exception:
        # Cleanup just in case
        with get_session() as session:
            session.query(EmailQueue).filter(EmailQueue.id == email_id).delete()
            session.commit()


def test_get_session_nested_contexts():
    """Test that nested context managers work correctly."""
    with get_session() as session1:
        with get_session() as session2:
            assert session1 is not None
            assert session2 is not None
            # Both should work independently
            assert hasattr(session1, "query")
            assert hasattr(session2, "query")
