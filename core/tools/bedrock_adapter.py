"""
Bedrock API adapter for tool definitions.

Provides get_tools_for_bedrock to format tools for AWS Bedrock Converse API,
removing tags that are not supported by the Bedrock API format.
"""

import copy
from typing import Any, Dict, List

from .definitions import TOOLS


def get_tools_for_bedrock() -> List[Dict[str, Any]]:
    """
    Get tools formatted for Bedrock Converse API (without tags).

    Bedrock Converse API doesn't accept 'tags' in toolSpec, so we remove them
    before sending to Bedrock. Tags are kept in TOOLS for MCP protocol use.

    Returns:
        List of tools with tags removed, suitable for Bedrock API
    """
    bedrock_tools = []
    for tool in TOOLS:
        # Deep copy to avoid modifying original
        tool_copy = copy.deepcopy(tool)

        # Remove tags from toolSpec if present
        if "toolSpec" in tool_copy and "tags" in tool_copy["toolSpec"]:
            del tool_copy["toolSpec"]["tags"]

        bedrock_tools.append(tool_copy)

    return bedrock_tools
