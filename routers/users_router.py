"""
Users Router.

Provides basic user profile management and RBAC metadata endpoints.

Notes:
  - This is intentionally separate from `/auth` (token issuance/refresh).
  - Endpoints are designed for admin workflows (multi-user / multi-role setups).

TODO:
  - Enforce auth/role checks consistently when AUTH is enabled.

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from models.database import get_session
from models.users import User, get_default_roles, normalize_permissions

logger = logging.getLogger(__name__)
router = APIRouter()


class UserCreateRequest(BaseModel):
    """Create a user profile."""

    username: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    role: str = Field("user", description="Role name (e.g., admin/analyst/user)")
    permissions: Optional[List[str]] = Field(default=None)


class UserPermissionsUpdateRequest(BaseModel):
    """Update user permissions."""

    permissions: List[str] = Field(default_factory=list)


@router.get("/", summary="List Users")
async def list_users():
    """List all users."""
    with get_session() as session:
        users = session.query(User).order_by(User.created_at.desc()).all()
        return {
            "status": "success",
            "count": len(users),
            "users": [u.to_dict() for u in users],
        }


@router.post("/", summary="Create User")
async def create_user(request: UserCreateRequest):
    """Create a new user profile."""
    with get_session() as session:
        existing = (
            session.query(User)
            .filter((User.username == request.username) | (User.email == request.email))
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")

        user = User(
            id=str(uuid4()),
            username=request.username.strip(),
            email=request.email.strip().lower(),
            role=request.role.strip(),
            permissions=normalize_permissions(request.permissions),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(user)
        session.flush()
        return {"status": "success", "user": user.to_dict()}


@router.patch("/{user_id}/permissions", summary="Update User Permissions")
async def update_user_permissions(user_id: str, request: UserPermissionsUpdateRequest):
    """Update permissions for a user."""
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.permissions = normalize_permissions(request.permissions)
        user.updated_at = datetime.utcnow()
        session.add(user)
        return {"status": "success", "user": user.to_dict()}


@router.get("/roles", summary="List Roles")
async def list_roles():
    """List supported roles."""
    return {"status": "success", "roles": get_default_roles()}


@router.get("/health", summary="Users Service Health")
async def users_health():
    """Health endpoint for users service."""
    return {"status": "healthy", "service": "Users Service"}
