"""
Notification models.

This provides a centralized hub for multi-channel notifications (email/webhook/etc.).
Email delivery itself remains under the existing /email service; this module stores
notification state (unread/read) and routing metadata.

Author: Utku Gulbardak
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    String,
    Text,
)

from .database import Base


class Notification(Base):
    """A single notification event addressed to a user."""

    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(100), nullable=False, index=True)

    channel = Column(String(50), nullable=False, default="email", index=True)
    title = Column(String(300), nullable=True)
    body = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)

    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel": self.channel,
            "title": self.title,
            "body": self.body,
            "payload": self.payload or {},
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


class NotificationChannel(Base):
    """
    Per-user channel configuration.

    TODO: Add validation + secrets management for webhook URLs and tokens.
    """

    __tablename__ = "notification_channels"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(100), nullable=False, index=True)
    channel = Column(String(50), nullable=False, index=True)  # email/slack/webhook

    enabled = Column(Boolean, default=True, nullable=False, index=True)
    config = Column(JSON, nullable=True)  # e.g., {"webhook_url": "..."}
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel": self.channel,
            "enabled": self.enabled,
            "config": self.config or {},
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
