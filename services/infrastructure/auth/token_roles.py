"""
Role definitions and authorization logic for MCP token-based access control.

Provides the ROLES registry mapping role names to permission patterns, scope-based
permission filtering, tool allowlist resolution, and wildcard permission matching.
This module contains pure authorization logic with no I/O dependencies.
"""

import re
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Role definitions with permissions
# ---------------------------------------------------------------------------

ROLES: Dict[str, Dict[str, Any]] = {
    "admin": {
        "permissions": ["*"],  # All access
        "description": "Full system access",
    },
    "analyst": {
        "permissions": [
            "run_*_analysis",
            "read_query",
            "get_query_preview",
            "create_*_chart",
            "list_tables",
            "describe_table",
            "get_table_sample",
            "get_table_stats",
            "get_cached_query",
        ],
        "description": "Analysis and query access",
    },
    "viewer": {
        "permissions": [
            "get_*",
            "list_*",
            "describe_*",
            "get_query_preview",
            "get_table_sample",
        ],
        "description": "Read-only access",
    },
    "pipeline": {
        "permissions": [
            "refresh_master_shot_table",
            "get_master_table_progress",
            "schedule_job",
            "trigger_job",
        ],
        "description": "Service account for automated pipelines",
    },
    "monitor": {
        "permissions": [
            "get_*",
            "list_*",
            "check_health",
            "get_metrics",
            "query_audit_log",
        ],
        "description": "Monitoring and audit access",
    },
}

# ---------------------------------------------------------------------------
# Scope-to-permission mapping used by apply_scopes
# ---------------------------------------------------------------------------

SCOPE_PERMISSIONS: Dict[str, List[str]] = {
    "read_only": ["get_*", "list_*", "describe_*"],
    "query_only": ["read_query", "get_query_preview"],
    "analytics_only": ["run_*_analysis"],
    "visualization_only": ["create_*_chart"],
}

# ---------------------------------------------------------------------------
# Canonical tool list used by get_allowed_tools
# ---------------------------------------------------------------------------

ALL_TOOLS: List[str] = [
    "run_runrate_analysis",
    "run_roi_analysis",
    "run_ana_baba_analysis",
    "read_query",
    "download_query",
    "get_query_preview",
    "create_line_chart",
    "create_bar_chart",
    "create_scatter_chart",
    "create_pie_chart",
    "list_tables",
    "describe_table",
    "get_table_sample",
    "get_table_stats",
    "get_cached_query",
    "schedule_job",
    "trigger_job",
    "list_jobs",
    "get_job",
]


# ---------------------------------------------------------------------------
# Pure authorization functions
# ---------------------------------------------------------------------------


def _matches_pattern(pattern: str, value: str) -> bool:
    """
    Check whether a permission pattern matches a concrete value.

    Supports wildcard ``*`` in patterns (e.g. ``run_*_analysis``).

    Args:
        pattern: Permission pattern, possibly containing ``*``.
        value: Concrete permission or tool name to test.

    Returns:
        True if *value* matches *pattern*.
    """
    if "*" in pattern:
        regex = pattern.replace("*", ".*")
        return bool(re.match(f"^{regex}$", value))
    return pattern == value


def check_permission(token_payload: Dict[str, Any], tool_name: str) -> bool:
    """
    Check if a token payload grants permission to use a given tool.

    Evaluates exact matches first, then wildcard patterns.  The ``*``
    permission (admin) grants access to everything.

    Args:
        token_payload: Validated token payload containing a ``permissions`` list.
        tool_name: Tool name to check.

    Returns:
        True if the payload permits the tool.
    """
    permissions: List[str] = token_payload.get("permissions", [])

    # Admin has all permissions
    if "*" in permissions:
        return True

    # Check exact match
    if tool_name in permissions:
        return True

    # Check wildcard patterns
    for permission in permissions:
        if "*" in permission and _matches_pattern(permission, tool_name):
            return True

    return False


def apply_scopes(permissions: List[str], scopes: List[str]) -> List[str]:
    """
    Filter permissions through the requested scopes for granular control.

    When *scopes* is non-empty, only those base permissions that match at
    least one scope pattern are retained.

    Args:
        permissions: Base permissions from role.
        scopes: Scopes to apply (e.g. ``["read_only", "query_only"]``).

    Returns:
        Filtered permission list.  Returns *permissions* unchanged when
        *scopes* is empty.
    """
    if not scopes:
        return permissions

    scoped_perms: List[str] = []
    for scope in scopes:
        if scope in SCOPE_PERMISSIONS:
            scoped_perms.extend(SCOPE_PERMISSIONS[scope])

    if not scoped_perms:
        return permissions

    filtered: List[str] = []
    for perm in permissions:
        for scoped_perm in scoped_perms:
            if _matches_pattern(scoped_perm, perm):
                filtered.append(perm)
                break

    return filtered


def get_allowed_tools(permissions: List[str]) -> List[str]:
    """
    Resolve the concrete tool names a permission set grants access to.

    Iterates over ``ALL_TOOLS`` and keeps those passing
    :func:`check_permission`.

    Args:
        permissions: List of permission patterns.

    Returns:
        List of allowed tool names.
    """
    payload: Dict[str, Any] = {"permissions": permissions}
    return [tool for tool in ALL_TOOLS if check_permission(payload, tool)]
