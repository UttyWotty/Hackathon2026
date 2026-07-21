"""
Tools package for Claude/Bedrock API integration.

Provides unified access to tool definitions, execution logic, email functionality,
and Bedrock API adapter. All exports maintain backward compatibility with tools_config.py.
"""

from .bedrock_adapter import get_tools_for_bedrock
from .definitions import (
    ANALYTICS_TOOLS,
    COMMUNICATION_TOOLS,
    DATA_TOOLS,
    PRESENTATION_TOOLS,
    SCHEDULER_TOOLS,
    TOOLS,
    VISUALIZATION_TOOLS,
)
from .email_sender import send_email_with_attachments
from .executor import execute_tool, execute_tool_async

__all__ = [
    # Main exports (backward compatible)
    "TOOLS",
    "execute_tool",
    "execute_tool_async",
    "get_tools_for_bedrock",
    "send_email_with_attachments",
    # Domain-specific tool lists
    "ANALYTICS_TOOLS",
    "DATA_TOOLS",
    "VISUALIZATION_TOOLS",
    "COMMUNICATION_TOOLS",
    "SCHEDULER_TOOLS",
    "PRESENTATION_TOOLS",
]
