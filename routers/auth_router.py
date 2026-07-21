"""
Auth Router - Authentication & Authorization (DISABLED BY DEFAULT)

Provides authentication capabilities:
- JWT token generation
- Token validation
- User management
- Role-based access control

⚠️ DISABLED BY DEFAULT - Enable via AUTH_ENABLED=True in .env

Uses: services/infrastructure/auth/
"""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from utils.error_handling import sanitize_error_message

# Check if auth is enabled
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "False").lower() == "true"

logger = logging.getLogger(__name__)

router = APIRouter()

# Only import auth modules if enabled
if AUTH_ENABLED:
    try:
        from services.infrastructure.auth.token_manager import TokenManager

        token_mgr = TokenManager()
        logger.info("✅ Authentication enabled - TokenManager initialized")
    except ImportError as e:
        logger.error(f"❌ Failed to import auth modules: {e}")
        AUTH_ENABLED = False
        token_mgr = None
else:
    token_mgr = None
    logger.info("ℹ️  Authentication disabled - Set AUTH_ENABLED=True in .env to enable")


# Request Models
class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    mfa_code: Optional[str] = Field(None, description="MFA code (if enabled)")


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token")


class CreateUserRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    email: str = Field(..., description="Email")
    role: str = Field("user", description="User role: 'admin', 'analyst', 'viewer'")


@router.get("/", summary="Auth Service Info")
async def auth_info():
    """Get information about the authentication service."""
    return {
        "service": "Authentication Service",
        "enabled": AUTH_ENABLED,
        "description": "JWT-based authentication and authorization",
        "status": "active" if AUTH_ENABLED else "disabled",
        "capabilities": (
            [
                "JWT Token Generation",
                "Token Validation & Refresh",
                "User Management",
                "Role-Based Access Control (RBAC)",
                "MFA Support (when enabled)",
            ]
            if AUTH_ENABLED
            else ["Disabled - Set AUTH_ENABLED=True to enable"]
        ),
        "roles": (
            {
                "admin": "Full system access",
                "analyst": "Run analyses, view reports",
                "viewer": "View-only access",
            }
            if AUTH_ENABLED
            else {}
        ),
        "how_to_enable": {
            "step_1": "Add AUTH_ENABLED=True to .env",
            "step_2": "Restart the server",
            "step_3": "Use POST /auth/login to get tokens",
            "step_4": "Include token in Authorization header",
        },
    }


@router.post("/login", summary="Login")
async def login(request: LoginRequest):
    """
    Login and receive JWT tokens.

    ⚠️ Only available if AUTH_ENABLED=True

    Returns:
    - access_token: Short-lived token for API requests
    - refresh_token: Long-lived token for refreshing access

    Include access_token in requests: `Authorization: Bearer <token>`
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Authentication is disabled. Set AUTH_ENABLED=True in .env to enable.",
        )

    try:
        # Validate credentials (would check against database in production)
        # For now, simple validation
        if not request.username or not request.password:
            raise HTTPException(
                status_code=400, detail="Username and password required"
            )

        # Generate tokens
        tokens = token_mgr.generate_token(
            user_id=request.username,
            role="admin",  # Would lookup from database
            additional_claims={"email": f"{request.username}@company.com"},
        )

        return {
            "status": "success",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "Bearer",
            "expires_in": tokens.get("expires_in", 3600),
            "user": {
                "username": request.username,
                "role": "admin",
            },
            "message": "Login successful",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Login failed. Please check your credentials and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/refresh", summary="Refresh Token")
async def refresh_token(request: TokenRefreshRequest):
    """
    Refresh access token using refresh token.

    ⚠️ Only available if AUTH_ENABLED=True

    Use when access token expires to get a new one without logging in again.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Authentication is disabled. Set AUTH_ENABLED=True in .env to enable.",
        )

    try:
        # Refresh token (would validate against database in production)
        new_tokens = token_mgr.refresh_token(request.refresh_token)

        return {
            "status": "success",
            "access_token": new_tokens["access_token"],
            "refresh_token": new_tokens.get("refresh_token", request.refresh_token),
            "token_type": "Bearer",
            "expires_in": new_tokens.get("expires_in", 3600),
            "message": "Token refreshed successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


@router.get("/user", summary="Get Current User")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Get information about the currently authenticated user.

    ⚠️ Only available if AUTH_ENABLED=True

    Requires: Authorization: Bearer <access_token>
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Authentication is disabled. Set AUTH_ENABLED=True in .env to enable.",
        )

    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401, detail="Missing or invalid authorization header"
            )

        token = authorization.split(" ")[1]

        # Validate token
        payload = token_mgr.validate_token(token)

        return {
            "status": "success",
            "user": {
                "user_id": payload.get("user_id"),
                "role": payload.get("role"),
                "email": payload.get("email"),
            },
            "token_expires": payload.get("exp"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/users", summary="Create User (Admin Only)")
async def create_user(
    request: CreateUserRequest, authorization: Optional[str] = Header(None)
):
    """
    Create a new user.

    ⚠️ Only available if AUTH_ENABLED=True
    ⚠️ Requires admin role

    Creates user with specified role and credentials.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Authentication is disabled. Set AUTH_ENABLED=True in .env to enable.",
        )

    try:
        # Validate admin token (would check role in production)
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Admin authentication required")

        token = authorization.split(" ")[1]
        payload = token_mgr.validate_token(token)

        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")

        # Create user (would store in database in production)
        user_data = {
            "username": request.username,
            "email": request.email,
            "role": request.role,
            "created_at": datetime.now().isoformat(),
        }

        return {
            "status": "success",
            "user": user_data,
            "message": f"User '{request.username}' created successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create user error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to create user. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/health", summary="Auth Service Health")
async def health_check():
    """Check if auth service is operational."""
    try:
        components_status = {
            "authentication": "enabled" if AUTH_ENABLED else "disabled",
            "token_manager": "ready" if token_mgr else "not_initialized",
        }

        overall_status = "healthy" if AUTH_ENABLED and token_mgr else "disabled"

        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "enabled": AUTH_ENABLED,
            "components": components_status,
            "message": (
                "Auth enabled - tokens required for API access"
                if AUTH_ENABLED
                else "Auth disabled - all endpoints are public"
            ),
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
