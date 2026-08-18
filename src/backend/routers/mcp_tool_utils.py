"""MCP Tool Utility Functions - Pure helpers for tool format conversion and filtering.

Provides conversion from Bedrock Converse API tool format to MCP protocol format,
tag-based filtering across multiple dimensions, and tag extraction/aggregation.
These are pure functions with no route definitions or I/O side effects.
"""

import logging
from typing import Any, Dict, List, Optional

from core.tools_config import TOOLS

logger = logging.getLogger(__name__)


def convert_bedrock_to_mcp_tool(bedrock_tool: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Bedrock Converse API tool format to MCP protocol format.

    Args:
        bedrock_tool: Tool definition in Bedrock format

    Returns:
        Tool definition in MCP format with tags
    """
    tool_spec = bedrock_tool.get("toolSpec", {})
    input_schema = tool_spec.get("inputSchema", {}).get("json", {})

    mcp_tool: Dict[str, Any] = {
        "name": tool_spec.get("name"),
        "description": tool_spec.get("description", ""),
        "inputSchema": {
            "type": "object",
            "properties": input_schema.get("properties", {}),
            "required": input_schema.get("required", []),
        },
    }

    # Include tags if present
    if "tags" in tool_spec:
        mcp_tool["tags"] = tool_spec["tags"]

    return mcp_tool


def filter_tools_by_tags(
    tools: List[Dict[str, Any]],
    tags: Optional[List[str]] = None,
    server: Optional[str] = None,
    domain: Optional[str] = None,
    operation: Optional[str] = None,
    exclude_tags: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter tools by tag criteria.

    Args:
        tools: List of tools to filter
        tags: List of tag values to match (matches any tag dimension)
        server: Filter by server tag
        domain: Filter by domain tag
        operation: Filter by operation tag
        exclude_tags: List of tag values to exclude

    Returns:
        Filtered list of tools
    """
    filtered = tools

    # Filter by server
    if server:
        filtered = [
            t
            for t in filtered
            if t.get("tags", {}).get("server", "").lower() == server.lower()
        ]

    # Filter by domain
    if domain:
        filtered = [
            t
            for t in filtered
            if t.get("tags", {}).get("domain", "").lower() == domain.lower()
        ]

    # Filter by operation
    if operation:
        filtered = [
            t
            for t in filtered
            if t.get("tags", {}).get("operation", "").lower() == operation.lower()
        ]

    # Filter by any tag value (searches across all tag dimensions)
    if tags:
        tag_set = {tag.lower() for tag in tags}
        filtered = [
            t
            for t in filtered
            if any(
                tag_value.lower() in tag_set for tag_value in t.get("tags", {}).values()
            )
        ]

    # Exclude tags
    if exclude_tags:
        exclude_set = {tag.lower() for tag in exclude_tags}
        filtered = [
            t
            for t in filtered
            if not any(
                tag_value.lower() in exclude_set
                for tag_value in t.get("tags", {}).values()
            )
        ]

    return filtered


TAG_DIMENSION_MAPPING: Dict[str, str] = {
    "server": "servers",
    "domain": "domains",
    "operation": "operations",
    "environment": "environments",
    "security": "security",
}

DEFAULT_TAG_DIMENSIONS: List[str] = [
    "servers",
    "domains",
    "operations",
    "environments",
    "security",
]


def _process_tool_tags(tags: Dict[str, Any], tag_dimensions: Dict[str, set]) -> None:
    """Process tags from a single tool and add to tag dimensions.

    Args:
        tags: Tags dictionary from a tool
        tag_dimensions: Dictionary of tag dimensions to update (mutated in place)
    """
    for tag_key, dimension_key in TAG_DIMENSION_MAPPING.items():
        if tag_key in tags:
            tag_dimensions[dimension_key].add(tags[tag_key])


def _format_tag_dimensions(tag_dimensions: Dict[str, set]) -> Dict[str, List[str]]:
    """Convert tag dimensions from sets to sorted lists.

    Args:
        tag_dimensions: Dictionary with sets as values

    Returns:
        Dictionary with sorted lists as values
    """
    return {dimension: sorted(values) for dimension, values in tag_dimensions.items()}


def get_all_tags(tools: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Extract all unique tags from tools.

    Args:
        tools: List of tools

    Returns:
        Dictionary with tag dimensions as keys and lists of unique values
    """
    tag_dimensions: Dict[str, set] = {dim: set() for dim in DEFAULT_TAG_DIMENSIONS}

    for tool in tools:
        tags = tool.get("tags", {})
        if tags:
            _process_tool_tags(tags, tag_dimensions)

    return _format_tag_dimensions(tag_dimensions)


def get_mcp_tools() -> List[Dict[str, Any]]:
    """Get all tools in MCP protocol format.

    Returns:
        List of tools in MCP format
    """
    mcp_tools: List[Dict[str, Any]] = []
    for bedrock_tool in TOOLS:
        try:
            mcp_tool = convert_bedrock_to_mcp_tool(bedrock_tool)
            if mcp_tool.get("name"):
                mcp_tools.append(mcp_tool)
        except Exception as e:
            logger.warning("Failed to convert tool to MCP format: %s", e)
            continue

    return mcp_tools
