"""
Tool definitions and LLM-format adapters for the autonomous agent.

Re-exports TOOLS from core/tools/definitions and provides get_tools_for_llm()
which formats them for the Cortex Messages API.
"""

from typing import Any, Dict, List

from core.tools.definitions import TOOLS
from core.tools.email_sender import send_email_with_attachments

__all__ = [
    "TOOLS",
    "get_tools_for_llm",
    "send_email_with_attachments",
]


def get_tools_for_llm() -> List[Dict[str, Any]]:
    """Return tool definitions formatted for Snowflake Cortex Messages API."""
    from core.tools.cortex_adapter import get_tools_for_cortex

    return get_tools_for_cortex()
