"""
User and role models.

These models provide persistent user profiles and RBAC metadata. They are
intentionally lightweight: authentication token issuance still lives under
`services/infrastructure/auth/`, while this module stores user identities and
permissions that can be enforced by routers/services.

Author: Utku Gulbardak
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    String,
)

from .database import Base


class User(Base):
    """
    Persistent user profile.

    Notes:
      - This is not a password store. Passwords should never be stored in plain text.
      - Token issuance/validation is handled by the TokenManager.
    """

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)  # UUID
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)

    role = Column(String(50), nullable=False, default="user", index=True)
    permissions = Column(JSON, nullable=True)  # e.g., ["backup_restore", "admin:*"]

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dict for API responses."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "permissions": self.permissions or [],
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def get_default_roles() -> List[Dict[str, Any]]:
    """
    Get the supported roles for the API.

    Returns:
        List of role descriptors.
    """
    return [
        {"name": "admin", "description": "Full access"},
        {"name": "analyst", "description": "Analytics + read access"},
        {"name": "user", "description": "Basic access"},
    ]


def normalize_permissions(permissions: Optional[List[str]]) -> List[str]:
    """
    Normalize permissions list for storage.

    Args:
        permissions: Incoming permissions list.

    Returns:
        Cleaned permissions list.
    """
    if not permissions:
        return []
    return sorted({p.strip() for p in permissions if p and p.strip()})
