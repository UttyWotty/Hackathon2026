"""
Authentication and Audit Decorators for MCP Servers.

Provides decorators to secure MCP tools with authentication and audit logging.

Author: Utku Gulbardak
Date: 2025-11-12
"""

import functools
import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def require_auth(
    require_role: Optional[str] = None,
    allow_anonymous: bool = False,
):
    """
    Decorator to require authentication for MCP tool.

    Args:
        require_role: Required role (None = any authenticated user)
        allow_anonymous: Allow anonymous access if auth is disabled

    Example:
        @require_auth(require_role="admin")
        async def sensitive_tool(**kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if auth is enabled
            auth_enabled = os.getenv("AUTH_ENABLED", "false").lower() == "true"

            if not auth_enabled:
                if allow_anonymous:
                    logger.debug(
                        f"Auth disabled, allowing anonymous access to {func.__name__}"
                    )
                    return await func(*args, **kwargs)
                else:
                    return {
                        "status": "error",
                        "error": "Authentication is disabled. Set AUTH_ENABLED=true to use this tool.",
                    }

            # Get token from kwargs
            token = kwargs.get("token") or kwargs.get("auth_token")

            if not token:
                return {
                    "status": "error",
                    "error": "Authentication required. Please provide 'token' parameter.",
                    "hint": "Get a token using the Auth MCP Server: generate_api_token",
                }

            # Validate token
            try:
                from services.infrastructure.auth.token_manager import get_token_manager

                token_manager = get_token_manager()
                token_payload = token_manager.validate_token(token)

                # Check role if required
                if require_role:
                    user_role = token_payload.get("role")
                    if user_role != require_role and user_role != "admin":
                        return {
                            "status": "error",
                            "error": f"Insufficient permissions. Required role: {require_role}",
                            "your_role": user_role,
                        }

                # Check tool permission
                tool_name = func.__name__
                if not token_manager.check_permission(token_payload, tool_name):
                    return {
                        "status": "error",
                        "error": f"You don't have permission to use '{tool_name}'",
                        "your_role": token_payload.get("role"),
                        "your_permissions": token_payload.get("permissions", []),
                    }

                # Add token payload to kwargs for use in function
                kwargs["_auth_user"] = token_payload

                # Remove token from kwargs to avoid exposing it
                kwargs.pop("token", None)
                kwargs.pop("auth_token", None)

                # Call function
                return await func(*args, **kwargs)

            except ValueError as e:
                return {
                    "status": "error",
                    "error": f"Authentication failed: {str(e)}",
                }
            except Exception as e:
                logger.error(f"Auth error in {func.__name__}: {e}")
                return {
                    "status": "error",
                    "error": f"Authentication error: {str(e)}",
                }

        return wrapper

    return decorator


def audit_log(
    mcp_server: str,
    estimate_credits: bool = False,
):
    """
    Decorator to automatically log MCP tool calls to audit log.

    Args:
        mcp_server: MCP server name (e.g., "analytics-mcp")
        estimate_credits: Whether to estimate Snowflake credits

    Example:
        @audit_log(mcp_server="analytics-mcp")
        async def run_analysis(**kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if audit logging is enabled
            audit_enabled = os.getenv("AUDIT_LOGGING_ENABLED", "true").lower() == "true"

            if not audit_enabled:
                # Just run the function without logging
                return await func(*args, **kwargs)

            # Start timer
            start_time = time.time()

            # Get user info from auth payload (if available)
            auth_user = kwargs.get("_auth_user", {})
            user_id = auth_user.get("user_id", "anonymous")
            email = auth_user.get("email", "unknown")
            role = auth_user.get("role", "unknown")

            # Prepare arguments for logging (remove internal fields)
            log_args = {k: v for k, v in kwargs.items() if not k.startswith("_")}

            # Execute function
            result = None
            status = "success"
            error_message = None
            rows_returned = None

            try:
                result = await func(*args, **kwargs)

                # Extract metrics from result
                if isinstance(result, dict):
                    if result.get("status") == "error":
                        status = "error"
                        error_message = result.get("error", "Unknown error")

                    # Try to get row count
                    rows_returned = result.get("rows") or result.get("row_count")

                    # Some results have nested data
                    if "data" in result and isinstance(result["data"], list):
                        rows_returned = len(result["data"])

                return result

            except Exception as e:
                status = "error"
                error_message = str(e)
                logger.error(f"Error in {func.__name__}: {e}")
                raise

            finally:
                # Calculate execution time
                execution_time_ms = (time.time() - start_time) * 1000

                # Estimate Snowflake credits (very rough estimate)
                snowflake_credits = None
                if estimate_credits and execution_time_ms:
                    # Rough estimate: $2 per compute-hour, 400 credits per dollar
                    # So ~0.0002 credits per second
                    snowflake_credits = (execution_time_ms / 1000) * 0.0002

                # Log to audit (SQLite-based)
                try:
                    from services.infrastructure.audit.sqlite_logger import (
                        log_audit_event,
                    )

                    log_audit_event(
                        service=mcp_server,
                        tool_name=func.__name__,
                        user_id=user_id,
                        status=status,
                        execution_time_ms=execution_time_ms,
                        error_message=error_message,
                        metadata={
                            "arguments": log_args,
                            "email": email,
                            "role": role,
                            "rows_returned": rows_returned,
                            "snowflake_credits": snowflake_credits,
                        },
                    )
                except Exception as e:
                    logger.error(f"Failed to log audit event: {e}")

        return wrapper

    return decorator


def secure_tool(
    mcp_server: str,
    require_role: Optional[str] = None,
    allow_anonymous: bool = True,
    estimate_credits: bool = False,
):
    """
    Combined decorator for auth + audit logging.

    Args:
        mcp_server: MCP server name
        require_role: Required role (None = any authenticated user)
        allow_anonymous: Allow anonymous if auth disabled
        estimate_credits: Estimate Snowflake credits

    Example:
        @secure_tool(mcp_server="analytics-mcp", require_role="analyst")
        async def run_analysis(**kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Apply decorators in order: audit (outer) -> auth (inner)
        func = require_auth(require_role=require_role, allow_anonymous=allow_anonymous)(
            func
        )
        func = audit_log(mcp_server=mcp_server, estimate_credits=estimate_credits)(func)
        return func

    return decorator
