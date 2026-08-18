"""MCP tool adapter modules for the insights feature.

Each module exposes plain functions matching MCP tool signatures, registered in the
tool dispatcher registry (services/infrastructure/scheduler/tool_dispatcher.py).
Adapters fetch from Snowflake/SQLite and delegate computation to analysis/insights.
"""
