"""
Tool definitions and execution entry point for Claude/Bedrock integration.
Re-exports TOOLS, execution functions, and email from core.tools subpackage.
All definitions live in core/tools/definitions.py; execution in core/tools/executor.py.
"""

from typing import Any, Dict, List

# Tool definitions (single source of truth in core/tools/definitions.py)
from core.tools.definitions import TOOLS

# Email helper (single source of truth in core/tools/email_sender.py)
from core.tools.email_sender import send_email_with_attachments

# Execution functions (single source of truth in core/tools/executor.py)
from core.tools.executor import execute_tool, execute_tool_async

# Public API re-exported for callers that import from core.tools_config.
# Listed in __all__ so the re-exports are not flagged as unused imports.
__all__ = [
    "TOOLS",
    "get_tools_for_bedrock",
    "get_tools_for_llm",
    "execute_tool",
    "execute_tool_async",
    "send_email_with_attachments",
]


def get_tools_for_bedrock() -> List[Dict[str, Any]]:
    """Return tool definitions in Bedrock Converse API format.

    Returns:
        List of tool spec dictionaries consumable by AWS Bedrock.
    """
    return TOOLS


def get_tools_for_llm() -> List[Dict[str, Any]]:
    """Return tool definitions for the active LLM backend.

    Both backends take Anthropic-format tools: Cortex natively, and the MLX
    client converts them down to OpenAI function format on the way out.

    Returns:
        List of tool definitions with name, description and input_schema.
    """
    from core.tools.cortex_adapter import get_tools_for_cortex

    return get_tools_for_cortex()
