"""
Tools package for Cortex/Claude API integration.

Provides unified access to tool definitions and email functionality.
"""

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

__all__ = [
    "TOOLS",
    "send_email_with_attachments",
    "ANALYTICS_TOOLS",
    "DATA_TOOLS",
    "VISUALIZATION_TOOLS",
    "COMMUNICATION_TOOLS",
    "SCHEDULER_TOOLS",
    "PRESENTATION_TOOLS",
]
