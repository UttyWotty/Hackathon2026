"""
Tool definitions and LLM-format adapters for the autonomous agent.

Re-exports TOOLS from core/tools/definitions.py and provides get_tools_for_llm()
which formats them for whichever backend (Cortex or MLX) is active.
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
    """Return tool definitions for the active LLM backend.

    Both backends take Anthropic-format tools: Cortex natively, and the MLX
    client converts them down to OpenAI function format on the way out.
    """
    from core.tools.cortex_adapter import get_tools_for_cortex

    return get_tools_for_cortex()
