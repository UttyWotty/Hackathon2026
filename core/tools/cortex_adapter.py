"""
Cortex Messages API adapter for tool definitions.

Provides get_tools_for_cortex, which converts the repository's Bedrock-shaped
TOOLS registry into the Anthropic tool format the Cortex Messages API expects.
This is the Cortex sibling of bedrock_adapter.py and is pure, doing no I/O.
"""

from typing import Any, Dict, List

from ..cortex_errors import CortexResponseError
from .definitions import TOOLS

# Keys in the source (Bedrock) tool registry.
TOOL_SPEC_KEY = "toolSpec"
INPUT_SCHEMA_KEY = "inputSchema"
INPUT_SCHEMA_JSON_KEY = "json"

# Tags are carried in TOOLS for MCP protocol use and are not part of either
# wire format, so they are dropped here exactly as bedrock_adapter drops them.
TAGS_KEY = "tags"

# Fallback schema for a tool that declares no inputs, since Anthropic requires
# input_schema to be present and object-typed.
EMPTY_INPUT_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {}}


def convert_tool_to_cortex(tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single Bedrock-shaped tool definition to Anthropic format.

    Bedrock nests the JSON Schema at toolSpec.inputSchema.json; Anthropic wants
    it flat under input_schema.

    Args:
        tool: One entry from the TOOLS registry.

    Returns:
        A dict with name, description and input_schema keys.

    Raises:
        CortexResponseError: If the entry has no toolSpec or no name.
    """
    spec = tool.get(TOOL_SPEC_KEY)
    if not isinstance(spec, dict):
        raise CortexResponseError(
            f"Tool definition is missing a '{TOOL_SPEC_KEY}' object: {tool!r}"
        )

    name = spec.get("name")
    if not name:
        raise CortexResponseError(f"Tool definition has no name: {tool!r}")

    schema = spec.get(INPUT_SCHEMA_KEY, {}).get(INPUT_SCHEMA_JSON_KEY)
    if not isinstance(schema, dict):
        schema = EMPTY_INPUT_SCHEMA

    return {
        "name": name,
        "description": spec.get("description", ""),
        "input_schema": schema,
    }


def get_tools_for_cortex() -> List[Dict[str, Any]]:
    """
    Get every registered tool formatted for the Cortex Messages API.

    Returns:
        The full TOOLS registry converted to Anthropic tool format, tags removed.
    """
    return [convert_tool_to_cortex(tool) for tool in TOOLS]
