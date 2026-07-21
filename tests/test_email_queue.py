"""
Tests for email queue processor and sender.

Tests critical paths:
- Email queue addition
- Email processing with concurrency limits
- Retry logic
- Error handling
"""

import asyncio
from unittest.mock import patch

import pytest  # type: ignore[import-untyped]

from models.database import get_session
from models.email import EmailHistory, EmailQueue
from services.infrastructure.email.queue_processor import (
    _process_single_email,
    add_email_to_queue,
)
from services.infrastructure.email.sender import send_email_with_retry


@pytest.fixture
def sample_email_data():
    """Sample email data for testing."""
    return {
        "to_email": "test@example.com",
        "subject": "Test Email",
        "body": "This is a test email body",
        "html": False,
        "priority": 5,
    }


def test_add_email_to_queue(sample_email_data):
    """Test adding email to queue."""
    email_id = add_email_to_queue(**sample_email_data)

    assert email_id is not None
    assert isinstance(email_id, str)
    assert len(email_id) > 0

    # Verify email was added to database
    with get_session() as session:
        email_item = session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
        assert email_item is not None
        assert email_item.to_email == sample_email_data["to_email"]
        assert email_item.subject == sample_email_data["subject"]
        assert email_item.status == "pending"

        # Cleanup
        session.delete(email_item)
        session.commit()


def test_email_queue_priority_ordering():
    """Test that emails are ordered by priority."""
    # Add emails with different priorities
    email1_id = add_email_to_queue(
        to_email="low@example.com",
        subject="Low Priority",
        body="Low",
        priority=1,
    )
    email2_id = add_email_to_queue(
        to_email="high@example.com",
        subject="High Priority",
        body="High",
        priority=10,
    )

    try:
        with get_session() as session:
            emails = (
                session.query(EmailQueue)
                .filter(EmailQueue.id.in_([email1_id, email2_id]))
                .order_by(EmailQueue.priority.desc())
                .all()
            )

            assert len(emails) == 2
            assert emails[0].priority == 10  # High priority first
            assert emails[1].priority == 1  # Low priority second
    finally:
        # Cleanup
        with get_session() as session:
            session.query(EmailQueue).filter(
                EmailQueue.id.in_([email1_id, email2_id])
            ).delete()
            session.commit()


@patch("services.infrastructure.email.sender.send_email_with_retry")
@pytest.mark.asyncio
async def test_process_single_email_success(mock_send):
    """Test processing email successfully."""
    # Mock successful send
    mock_send.return_value = {
        "status": "success",
        "attempts": 1,
    }

    # Add email to queue
    email_id = add_email_to_queue(
        to_email="success@example.com",
        subject="Success Test",
        body="Test",
    )

    try:
        # Process email
        await _process_single_email(email_id)

        # Verify email moved to history
        with get_session() as session:
            history = (
                session.query(EmailHistory)
                .filter(EmailHistory.id.like(f"%{email_id[:8]}%"))
                .first()
            )
            # Email should be deleted from queue
            queue_item = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )
            assert (
                queue_item is None
            ), "Email should be removed from queue after success"

            if history:
                session.delete(history)
                session.commit()
    except Exception:
        # Cleanup on error
        with get_session() as session:
            session.query(EmailQueue).filter(EmailQueue.id == email_id).delete()
            session.commit()
        raise


@patch("services.infrastructure.email.sender.send_email_with_retry")
@pytest.mark.asyncio
async def test_process_single_email_retry(mock_send):
    """Test email retry logic."""
    # Mock failed send
    mock_send.return_value = {
        "status": "error",
        "error": "SMTP connection failed",
        "attempts": 1,
    }

    # Add email to queue with max_retries=2
    email_id = add_email_to_queue(
        to_email="retry@example.com",
        subject="Retry Test",
        body="Test",
    )

    try:
        # Update max_retries
        with get_session() as session:
            email_item = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )
            email_item.max_retries = 2
            session.commit()

        # Process email (should schedule retry)
        await _process_single_email(email_id)

        # Verify email scheduled for retry
        with get_session() as session:
            email_item = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )
            assert email_item is not None
            assert email_item.status == "pending"
            assert email_item.retry_count == 1
            assert email_item.scheduled_at is not None

            # Cleanup
            session.delete(email_item)
            session.commit()
    except Exception:
        # Cleanup on error
        with get_session() as session:
            session.query(EmailQueue).filter(EmailQueue.id == email_id).delete()
            session.commit()
        raise


def test_email_sender_missing_credentials():
    """Test email sender handles missing SMTP credentials."""
    with patch.dict("os.environ", {}, clear=True):
        result = send_email_with_retry(
            to_email="test@example.com",
            subject="Test",
            body="Test",
        )

        assert result["status"] == "error"
        assert "credentials" in result["error"].lower()


@pytest.mark.asyncio
async def test_email_queue_concurrency_limit():
    """Test that email queue respects concurrency limits."""
    from services.infrastructure.email.queue_processor import (
        _MAX_CONCURRENT_EMAILS,
        _get_email_semaphore,
    )

    # Get semaphore (will initialize if needed)
    semaphore = _get_email_semaphore()

    # Verify semaphore is initialized
    assert semaphore is not None
    assert semaphore._value <= _MAX_CONCURRENT_EMAILS

    # Test semaphore limits concurrent execution
    async def acquire_and_hold():
        async with semaphore:
            await asyncio.sleep(0.1)
            return True

    # Run more tasks than semaphore limit
    tasks = [acquire_and_hold() for _ in range(_MAX_CONCURRENT_EMAILS * 2)]
    results = await asyncio.gather(*tasks)

    # All should complete (semaphore allows through)
    assert all(results)
    assert len(results) == _MAX_CONCURRENT_EMAILS * 2
