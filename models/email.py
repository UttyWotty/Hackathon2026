"""
Email queue and history database models.

Stores email queue for persistent background sending and email history for tracking.
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from .database import Base


class EmailQueue(Base):
    """
    Email queue model for persistent background email sending.

    Stores emails that need to be sent in the background, surviving server restarts.
    """

    __tablename__ = "email_queue"

    # Primary key
    id = Column(String(36), primary_key=True)  # UUID

    # Email content
    to_email = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    html = Column(Boolean, default=False, nullable=False)
    attachments = Column(JSON, nullable=True)  # List of file paths

    # Status tracking
    status = Column(
        String(50), default="pending", nullable=False, index=True
    )  # pending, processing, sent, failed
    priority = Column(
        Integer, default=5, nullable=False
    )  # 1-10, higher = more important
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    scheduled_at = Column(DateTime, nullable=True)  # When to send (for delayed emails)
    processed_at = Column(DateTime, nullable=True)

    # Error tracking
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0, nullable=False)

    # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name conflict)
    extra_metadata = Column(
        "metadata", JSON, nullable=True
    )  # Additional data (source, analysis_type, etc.)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "to_email": self.to_email,
            "subject": self.subject,
            "body": (
                self.body[:200] + "..." if len(self.body) > 200 else self.body
            ),  # Truncate for listing
            "html": self.html,
            "attachments": self.attachments,
            "status": self.status,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "scheduled_at": (
                self.scheduled_at.isoformat() if self.scheduled_at else None
            ),
            "processed_at": (
                self.processed_at.isoformat() if self.processed_at else None
            ),
            "last_error": self.last_error,
            "error_count": self.error_count,
            "metadata": self.extra_metadata,  # Keep 'metadata' key in dict for API compatibility
        }

    def __repr__(self):
        return f"<EmailQueue(id={self.id}, to={self.to_email}, status={self.status})>"


class EmailHistory(Base):
    """
    Email history model for tracking sent emails.

    Stores complete history of all sent emails for audit and compliance.
    """

    __tablename__ = "email_history"

    # Primary key
    id = Column(String(36), primary_key=True)  # UUID

    # Email content (snapshot at send time)
    to_email = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    body_preview = Column(Text, nullable=True)  # First 500 chars for quick reference
    html = Column(Boolean, default=False, nullable=False)
    attachments = Column(JSON, nullable=True)  # List of file paths

    # Delivery status
    status = Column(String(50), nullable=False, index=True)  # sent, failed, bounced
    delivery_status = Column(
        String(50), nullable=True
    )  # delivered, failed, bounced, etc.

    # Timestamps
    sent_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=1, nullable=False)

    # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name conflict)
    extra_metadata = Column(
        "metadata", JSON, nullable=True
    )  # Source, analysis_type, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "to_email": self.to_email,
            "subject": self.subject,
            "body_preview": self.body_preview,
            "html": self.html,
            "attachments": self.attachments,
            "status": self.status,
            "delivery_status": self.delivery_status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": (
                self.delivered_at.isoformat() if self.delivered_at else None
            ),
            "error_message": self.error_message,
            "attempts": self.attempts,
            "metadata": self.extra_metadata,  # Keep 'metadata' key in dict for API compatibility
        }

    def __repr__(self):
        return f"<EmailHistory(id={self.id}, to={self.to_email}, status={self.status})>"
