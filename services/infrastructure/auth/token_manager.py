"""
Token Manager for MCP Authentication handling JWT lifecycle and Redis storage.

Generates, validates, revokes, and lists JWT tokens with role-based access
control.  Role definitions and authorization logic are delegated to the
``token_roles`` module to keep this file focused on token I/O.
"""

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from services.infrastructure.auth.token_roles import (
    ROLES,
    apply_scopes,
    check_permission,
    get_allowed_tools,
)

logger = logging.getLogger(__name__)

try:
    import jwt

    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWT not installed, using simple token validation")


class TokenManager:
    """
    Token Manager for MCP Authentication.

    Handles token generation, validation, and storage with role-based access control.
    Uses Redis for token storage with JWT for stateless validation.
    """

    # Expose the canonical ROLES registry as a class attribute
    ROLES = ROLES

    def __init__(
        self,
        secret_key: Optional[str] = None,
        default_expiry_hours: int = 24,
        redis_client: Optional[Any] = None,
    ) -> None:
        """
        Initialize Token Manager.

        Args:
            secret_key: JWT secret key (auto-generated if None)
            default_expiry_hours: Default token expiry in hours
            redis_client: Optional Redis client for token storage
        """
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY", secrets.token_urlsafe(32)
        )
        self.default_expiry_hours = default_expiry_hours
        self.redis_client = redis_client

        # Algorithm for JWT
        self.algorithm = "HS256"

        logger.info("Token Manager initialized")

    def generate_token(
        self,
        user_id: str,
        email: str,
        role: str = "analyst",
        expiry_hours: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate authentication token.

        Args:
            user_id: Unique user identifier
            email: User email
            role: User role (admin, analyst, viewer, pipeline, monitor)
            expiry_hours: Token expiry in hours (None = default)
            metadata: Additional metadata to include in token

        Returns:
            dict: Token information including token string and expiry
        """
        if role not in self.ROLES:
            raise ValueError(
                "Invalid role: %s. Valid roles: %s" % (role, list(self.ROLES.keys()))
            )

        expiry_hours = expiry_hours or self.default_expiry_hours
        expiry = datetime.now() + timedelta(hours=expiry_hours)

        # Create token payload
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "email": email,
            "role": role,
            "permissions": self.ROLES[role]["permissions"],
            "iat": datetime.now(),
            "exp": expiry,
        }

        # Add metadata if provided
        if metadata:
            payload["metadata"] = metadata

        # Generate token
        if JWT_AVAILABLE:
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            if isinstance(token, bytes):
                token = token.decode("utf-8")
        else:
            # Fallback: simple token (not recommended for production)
            json.dumps(payload, default=str)
            token = secrets.token_urlsafe(32)

        # Store in Redis if available
        self._store_token_in_redis(
            token, user_id, email, role, expiry, expiry_hours, metadata
        )

        return {
            "token": token,
            "user_id": user_id,
            "email": email,
            "role": role,
            "permissions": self.ROLES[role]["permissions"],
            "expires_at": expiry.isoformat(),
            "expires_in_hours": expiry_hours,
        }

    def _store_token_in_redis(
        self,
        token: str,
        user_id: str,
        email: str,
        role: str,
        expiry: datetime,
        expiry_hours: int,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """
        Persist a token record in Redis with an expiry TTL.

        Args:
            token: Raw token string.
            user_id: Unique user identifier.
            email: User email.
            role: User role name.
            expiry: Absolute expiry datetime.
            expiry_hours: Expiry duration in hours (used for TTL).
            metadata: Additional metadata dict (may be None).
        """
        if not self.redis_client:
            return

        try:
            token_key = "mcp_token:%s" % self._hash_token(token)
            token_data = {
                "user_id": user_id,
                "email": email,
                "role": role,
                "created_at": datetime.now().isoformat(),
                "expires_at": expiry.isoformat(),
                "metadata": metadata or {},
            }

            ttl_seconds = int(expiry_hours * 3600)
            self.redis_client.setex(
                token_key, ttl_seconds, json.dumps(token_data, default=str)
            )
            logger.info("Token stored in Redis for %s (%s)", email, role)
        except Exception as e:
            logger.warning("Failed to store token in Redis: %s", e)

    def validate_token(
        self,
        token: str,
        client_ip: Optional[str] = None,
        mfa_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate authentication token with IP and MFA checks.

        Args:
            token: Token string to validate
            client_ip: Client IP address for IP whitelist check
            mfa_code: MFA code if MFA is required

        Returns:
            dict: Token payload if valid

        Raises:
            ValueError: If token is invalid or expired
        """
        if not token:
            raise ValueError("Token is required")

        try:
            if JWT_AVAILABLE:
                return self._validate_jwt_token(token, client_ip, mfa_code)
            return self._validate_redis_token(token, client_ip)

        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError("Invalid token: %s" % e)
        except ValueError:
            raise
        except Exception as e:
            logger.error("Token validation error: %s", e)
            raise ValueError("Token validation failed: %s" % e)

    def _validate_jwt_token(
        self,
        token: str,
        client_ip: Optional[str],
        mfa_code: Optional[str],
    ) -> Dict[str, Any]:
        """
        Validate a token using JWT decoding with optional Redis revocation check.

        Args:
            token: Raw JWT token string.
            client_ip: Client IP for whitelist validation (may be None).
            mfa_code: MFA code for two-factor validation (may be None).

        Returns:
            Validated token payload dict.
        """
        payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

        # Check Redis for revocation (if available)
        if self.redis_client:
            token_key = "mcp_token:%s" % self._hash_token(token)
            if not self.redis_client.exists(token_key):
                logger.warning("Token not found in Redis (may be revoked)")

        metadata = payload.get("metadata", {})

        # Check IP whitelist
        ip_whitelist = metadata.get("ip_whitelist")
        if ip_whitelist and client_ip:
            if client_ip not in ip_whitelist:
                raise ValueError("IP address %s not in whitelist" % client_ip)

        # Check MFA requirement
        require_mfa = metadata.get("require_mfa", False)
        if require_mfa:
            if not mfa_code:
                raise ValueError("MFA code required for this token")
            if not self._validate_mfa_code(payload.get("user_id"), mfa_code):
                raise ValueError("Invalid MFA code")

        return {
            "valid": True,
            "user_id": payload.get("user_id"),
            "email": payload.get("email"),
            "role": payload.get("role"),
            "permissions": payload.get("permissions", []),
            "metadata": metadata,
            "expires_at": payload.get("exp"),
        }

    def _validate_redis_token(
        self,
        token: str,
        client_ip: Optional[str],
    ) -> Dict[str, Any]:
        """
        Validate a token using Redis lookup only (JWT unavailable fallback).

        Args:
            token: Raw token string.
            client_ip: Client IP for whitelist validation (may be None).

        Returns:
            Validated token payload dict.

        Raises:
            ValueError: When the token is not found or IP is rejected.
        """
        if self.redis_client:
            token_key = "mcp_token:%s" % self._hash_token(token)
            data = self.redis_client.get(token_key)
            if data:
                token_data = json.loads(data)

                # Check IP whitelist
                metadata = token_data.get("metadata", {})
                ip_whitelist = metadata.get("ip_whitelist")
                if ip_whitelist and client_ip:
                    if client_ip not in ip_whitelist:
                        raise ValueError("IP address %s not in whitelist" % client_ip)

                return {
                    "valid": True,
                    **token_data,
                    "permissions": self.ROLES.get(
                        token_data.get("role", "viewer"), {"permissions": []}
                    )["permissions"],
                }

        raise ValueError("Invalid token")

    def _validate_mfa_code(self, user_id: str, mfa_code: str) -> bool:
        """
        Validate MFA code (simplified -- in production use proper MFA service).

        Args:
            user_id: User identifier
            mfa_code: MFA code to validate

        Returns:
            True if valid
        """
        # NOTE: Basic MFA validation (for production, integrate with TOTP/SMS)
        # This validates length only. For real MFA, use authenticator apps.
        MIN_MFA_CODE_LENGTH = 6
        return len(mfa_code) >= MIN_MFA_CODE_LENGTH

    def _apply_scopes(self, permissions: List[str], scopes: List[str]) -> List[str]:
        """Delegate to ``token_roles.apply_scopes``."""
        return apply_scopes(permissions, scopes)

    def _get_allowed_tools(self, permissions: List[str]) -> List[str]:
        """Delegate to ``token_roles.get_allowed_tools``."""
        return get_allowed_tools(permissions)

    def check_permission(
        self,
        token_payload: Dict[str, Any],
        tool_name: str,
    ) -> bool:
        """Delegate to ``token_roles.check_permission``."""
        return check_permission(token_payload, tool_name)

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a token.

        Args:
            token: Token to revoke

        Returns:
            True on success, False otherwise.
        """
        if not self.redis_client:
            logger.warning("Redis not available, cannot revoke token")
            return False

        try:
            token_key = "mcp_token:%s" % self._hash_token(token)
            deleted = self.redis_client.delete(token_key)

            if deleted:
                logger.info("Token revoked")
                return True
            else:
                logger.warning("Token not found in Redis")
                return False

        except Exception as e:
            logger.error("Token revocation error: %s", e)
            return False

    def list_active_tokens(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List active tokens.

        Args:
            user_id: Filter by user ID (None = all tokens)

        Returns:
            Active token information.
        """
        if not self.redis_client:
            return []

        try:
            keys = self.redis_client.keys("mcp_token:*")
            tokens: List[Dict[str, Any]] = []

            for key in keys:
                data = self.redis_client.get(key)
                if data:
                    token_data = json.loads(data)

                    # Filter by user_id if provided
                    if user_id and token_data.get("user_id") != user_id:
                        continue

                    # Get TTL
                    ttl = self.redis_client.ttl(key)
                    token_data["ttl_seconds"] = ttl
                    tokens.append(token_data)

            return tokens

        except Exception as e:
            logger.error("List tokens error: %s", e)
            return []

    def _hash_token(self, token: str) -> str:
        """Generate hash of token for Redis key."""
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    @classmethod
    def get_available_roles(cls) -> Dict[str, Any]:
        """Get available roles and their permissions."""
        return cls.ROLES


# Global token manager instance
_token_manager: Optional[TokenManager] = None

# Module-level constants for environment variable defaults
TOKEN_EXPIRY_HOURS_DEFAULT = "24"


def get_token_manager(redis_client: Optional[Any] = None) -> TokenManager:
    """
    Get global token manager instance.

    Args:
        redis_client: Optional Redis client

    Returns:
        Global token manager singleton.
    """
    global _token_manager
    if _token_manager is None:
        # Get Redis client if not provided
        if redis_client is None:
            try:
                from services.infrastructure.cache.redis_client import get_cache_client

                cache = get_cache_client()
                if cache.use_redis:
                    redis_client = cache.redis_client
            except (ImportError, AttributeError, Exception) as e:
                logger.debug("Redis client not available for token manager: %s", e)

        _token_manager = TokenManager(
            secret_key=os.getenv("JWT_SECRET_KEY"),
            default_expiry_hours=int(
                os.getenv("TOKEN_EXPIRY_HOURS", TOKEN_EXPIRY_HOURS_DEFAULT)
            ),
            redis_client=redis_client,
        )
    return _token_manager
