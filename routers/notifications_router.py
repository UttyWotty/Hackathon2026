"""
Notifications Router.

Central hub for notifications across channels (email/webhook/etc.).

Endpoints:
  - GET   /notifications/user/{user_id}
  - PATCH /notifications/{notification_id}/read
  - POST  /notifications/webhook

TODO:
  - Add authentication/authorization per user.
  - Add channel configuration management endpoints.

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from models.database import get_session
from models.notifications import Notification

logger = logging.getLogger(__name__)
router = APIRouter()


class WebhookNotificationRequest(BaseModel):
    """Webhook ingestion payload."""

    user_id: str = Field(..., description="Target user id")
    channel: str = Field("webhook", description="Channel name")
    title: Optional[str] = None
    body: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.get("/user/{user_id}", summary="List Notifications For User")
async def list_notifications(user_id: str, unread_only: bool = False):
    """List notifications for a user."""
    with get_session() as session:
        q = session.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            q = q.filter(Notification.is_read == False)  # noqa: E712
        items = q.order_by(Notification.created_at.desc()).limit(200).all()
        return {
            "status": "success",
            "count": len(items),
            "notifications": [n.to_dict() for n in items],
        }


@router.patch("/{notification_id}/read", summary="Mark Notification Read")
async def mark_read(notification_id: str):
    """Mark a notification as read."""
    with get_session() as session:
        notif = (
            session.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
        )
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found")
        notif.is_read = True
        notif.read_at = datetime.utcnow()
        session.add(notif)
        return {"status": "success", "notification": notif.to_dict()}


@router.post("/webhook", summary="Ingest Notification via Webhook")
async def ingest_webhook_notification(request: WebhookNotificationRequest):
    """Create a notification event from a webhook payload."""
    with get_session() as session:
        notif = Notification(
            id=str(uuid4()),
            user_id=request.user_id,
            channel=request.channel,
            title=request.title,
            body=request.body,
            payload=request.payload,
            is_read=False,
            created_at=datetime.utcnow(),
            read_at=None,
        )
        session.add(notif)
        session.flush()
        return {"status": "success", "notification": notif.to_dict()}
