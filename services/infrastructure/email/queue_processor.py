"""
Email Queue Processor - Background worker for persistent email queue.

Processes emails from the database queue, handles retries, and tracks delivery status.
Maintains separation of concerns: queue management is separate from email sending logic.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Global processor state
_queue_processor_running = False

# Concurrency control: Limit concurrent email processing to prevent SMTP overload
# Default: 3 concurrent emails (configurable via EMAIL_CONCURRENCY_LIMIT env var)
import os  # noqa: E402

_MAX_CONCURRENT_EMAILS = int(os.getenv("EMAIL_CONCURRENCY_LIMIT", "3"))
_email_semaphore = None  # Initialized in start_email_queue_processor


def _get_email_semaphore():
    """Get or create email semaphore (lazy initialization for asyncio compatibility)."""
    global _email_semaphore
    if _email_semaphore is None:
        _email_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EMAILS)
    return _email_semaphore


async def start_email_queue_processor():
    """
    Start the background email queue processor loop.

    This runs continuously, processing emails from the database queue.
    Maintains separation: queue logic here, sending logic in email_router.
    """
    global _queue_processor_running
    _queue_processor_running = True

    logger.info("📧 Email queue processor starting...")

    poll_interval = 30  # Check every 30 seconds

    while _queue_processor_running:
        try:
            await _process_email_queue()
            await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            logger.info("📧 Email queue processor cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Email queue processor error: {e}", exc_info=True)
            await asyncio.sleep(poll_interval)  # Continue despite errors


def stop_email_queue_processor():
    """Stop the email queue processor loop."""
    global _queue_processor_running
    _queue_processor_running = False
    logger.info("📧 Email queue processor stop requested")


async def _process_email_queue():
    """
    Process pending emails from the queue.

    Separation of concerns:
    - This module handles queue management (status, retries, scheduling)
    - Email sending logic is in routers/email_router.py
    """
    try:
        from models.database import get_session
        from models.email import EmailQueue

        with get_session() as session:
            now = datetime.now()

            # Find pending emails that are ready to send
            emails_to_process = (
                session.query(EmailQueue)
                .filter(EmailQueue.status == "pending")
                .filter(
                    (EmailQueue.scheduled_at.is_(None))
                    | (EmailQueue.scheduled_at <= now)
                )
                .order_by(EmailQueue.priority.desc(), EmailQueue.created_at.asc())
                .limit(10)  # Process up to 10 emails per cycle
                .all()
            )

            if emails_to_process:
                logger.info(
                    f"📧 Processing {len(emails_to_process)} email(s) from queue (max {_MAX_CONCURRENT_EMAILS} concurrent)"
                )

            # Process each email with concurrency limit
            for email_item in emails_to_process:
                asyncio.create_task(_process_single_email_with_semaphore(email_item.id))

    except Exception as e:
        logger.error(f"❌ Error processing email queue: {e}", exc_info=True)


async def _process_single_email_with_semaphore(email_id: str):
    """
    Process a single email with concurrency control.

    Uses semaphore to limit concurrent email processing.
    """
    semaphore = _get_email_semaphore()
    async with semaphore:
        await _process_single_email(email_id)


async def _process_single_email(email_id: str):
    """
    Process a single email from the queue.

    Args:
        email_id: Email queue item ID
    """
    try:
        from models.database import get_session
        from models.email import EmailHistory, EmailQueue
        from services.infrastructure.email.sender import send_email_with_retry

        with get_session() as session:
            email_item = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )

            if not email_item:
                logger.error(f"❌ Email {email_id} not found in queue")
                return

            # Mark as processing
            email_item.status = "processing"
            email_item.processed_at = datetime.now()
            session.commit()

        logger.info(f"📧 Sending email: {email_item.subject} to {email_item.to_email}")

        # Send email (using existing send logic from email_router)
        result = send_email_with_retry(
            to_email=email_item.to_email,
            subject=email_item.subject,
            body=email_item.body,
            html=email_item.html,
            attachments=email_item.attachments,
            retry_count=email_item.max_retries,
        )

        # Update queue status based on result
        with get_session() as session:
            email_item = (
                session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
            )

            if email_item:
                if result.get("status") == "success":
                    # Success - move to history and remove from queue
                    email_item.status = "sent"

                    # Create history record
                    history_record = EmailHistory(
                        id=str(uuid.uuid4()),
                        to_email=email_item.to_email,
                        subject=email_item.subject,
                        body_preview=email_item.body[:500],
                        html=email_item.html,
                        attachments=email_item.attachments,
                        status="sent",
                        delivery_status="sent",
                        sent_at=datetime.now(),
                        attempts=result.get("attempts", 1),
                        extra_metadata=email_item.extra_metadata,
                    )
                    session.add(history_record)

                    # Remove from queue
                    session.delete(email_item)

                    logger.info(f"✅ Email sent successfully: {email_item.to_email}")

                else:
                    # Failure - check retry logic
                    email_item.retry_count += 1
                    email_item.error_count += 1
                    email_item.last_error = result.get("error", "Unknown error")

                    if email_item.retry_count < email_item.max_retries:
                        # Schedule retry with exponential backoff
                        retry_delay_minutes = (
                            2**email_item.retry_count
                        )  # 2, 4, 8 minutes
                        email_item.scheduled_at = datetime.now() + timedelta(
                            minutes=retry_delay_minutes
                        )
                        email_item.status = "pending"
                        logger.warning(
                            f"⚠️  Email failed, scheduling retry {email_item.retry_count}/{email_item.max_retries} "
                            f"in {retry_delay_minutes}m: {email_item.to_email}"
                        )
                    else:
                        # Max retries exceeded - move to history as failed
                        email_item.status = "failed"

                        # Create history record for failed email
                        history_record = EmailHistory(
                            id=str(uuid.uuid4()),
                            to_email=email_item.to_email,
                            subject=email_item.subject,
                            body_preview=email_item.body[:500],
                            html=email_item.html,
                            attachments=email_item.attachments,
                            status="failed",
                            delivery_status="failed",
                            sent_at=datetime.now(),
                            attempts=email_item.retry_count,
                            error_message=email_item.last_error,
                            extra_metadata=email_item.extra_metadata,
                        )
                        session.add(history_record)

                        # Remove from queue
                        session.delete(email_item)

                        logger.error(
                            f"❌ Email failed after {email_item.max_retries} retries: {email_item.to_email}"
                        )

                session.commit()

    except Exception as e:
        logger.error(f"❌ Fatal error processing email {email_id}: {e}", exc_info=True)

        # Try to update email status to failed
        try:
            from models.database import get_session
            from models.email import EmailQueue

            with get_session() as session:
                email_item = (
                    session.query(EmailQueue).filter(EmailQueue.id == email_id).first()
                )
                if email_item:
                    email_item.status = "failed"
                    email_item.error_count += 1
                    email_item.last_error = str(e)[:500]
                    session.commit()
        except Exception as e:
            logger.warning(f"Failed to update email error status: {e}")


def add_email_to_queue(
    to_email: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: Optional[List[str]] = None,
    priority: int = 5,
    scheduled_at: Optional[datetime] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Add an email to the persistent queue.

    Separation of concerns: This function only handles queue management.
    Actual sending is handled by the queue processor.

    Args:
        to_email: Recipient email
        subject: Email subject
        body: Email body
        html: Whether body is HTML
        attachments: List of file paths
        priority: Priority (1-10, higher = more important)
        scheduled_at: When to send (None = send immediately)
        extra_metadata: Additional metadata

    Returns:
        Email queue item ID
    """
    try:
        from models.database import get_session
        from models.email import EmailQueue

        with get_session() as session:
            email_item = EmailQueue(
                id=str(uuid.uuid4()),
                to_email=to_email,
                subject=subject,
                body=body,
                html=html,
                attachments=attachments or [],
                priority=priority,
                scheduled_at=scheduled_at,
                extra_metadata=extra_metadata or {},
            )

            session.add(email_item)
            session.commit()

            email_id = email_item.id

        logger.info(f"📧 Email queued: {subject} to {to_email} (ID: {email_id})")
        return email_id

    except Exception as e:
        logger.error(f"❌ Failed to add email to queue: {e}", exc_info=True)
        raise
