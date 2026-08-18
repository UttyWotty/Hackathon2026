"""
Pure request-building and response-parsing for the Cortex Messages API.

Builds Anthropic-style Messages payloads and parses the responses back into the
exact shapes the existing agent loop already consumes, so chat_interface,
chat_router and websocket_chat need no changes when the client is swapped. This
module performs no I/O whatsoever and is therefore fully testable offline.
"""

import json
from typing import Any, Dict, List, Optional

from .cortex_errors import CortexResponseError

# Anthropic content block discriminators.
CONTENT_TYPE_TEXT = "text"
CONTENT_TYPE_TOOL_USE = "tool_use"
CONTENT_TYPE_TOOL_RESULT = "tool_result"

# Message roles.
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# The stop_reason value that means the model is requesting a tool call. Cortex
# and Bedrock happen to use the identical string, so the loop's comparison is
# unchanged by the port.
STOP_REASON_TOOL_USE = "tool_use"

# Prompt caching. Tools and system are ordered ahead of messages in the cached
# prefix, so a single breakpoint on the system block also caches the tool
# schema - which is the large stable prefix the agent loop resends every turn.
CACHE_CONTROL_EPHEMERAL = "ephemeral"

# Bedrock's helper joined multiple text blocks with a blank line. Preserved so
# response text is byte-identical across the two backends.
TEXT_BLOCK_SEPARATOR = "\n\n"

# extract_tool_uses returns this key rather than Anthropic's native "id".
# The three call sites all read tool_use.get("toolUseId"), so translating here
# keeps the port confined to this module. Do not "correct" this to "id".
TOOL_USE_ID_KEY = "toolUseId"


def build_messages_payload(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    tools: Optional[List[Dict[str, Any]]],
    model: str,
    max_tokens: int,
    temperature: float,
    enable_prompt_caching: bool,
) -> Dict[str, Any]:
    """
    Build the JSON body for POST /api/v2/cortex/v1/messages.

    Every value is passed in explicitly; this function reads no environment and
    applies no hidden defaults.

    Args:
        messages: Conversation turns in Anthropic format.
        system_prompt: System prompt text, sent as a single cacheable block.
        tools: Anthropic-format tool definitions, or None to omit the key.
        model: Cortex model id, e.g. the value from SHOW CORTEX BASE MODELS.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        enable_prompt_caching: Whether to attach an ephemeral cache breakpoint.

    Returns:
        The request body as a plain dictionary.
    """
    system_block: Dict[str, Any] = {
        "type": CONTENT_TYPE_TEXT,
        "text": system_prompt,
    }
    if enable_prompt_caching:
        system_block["cache_control"] = {"type": CACHE_CONTROL_EPHEMERAL}

    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": [system_block],
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
    return payload


def _content_blocks(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the assistant content blocks, raising if the payload is malformed."""
    if not isinstance(response, dict):
        raise CortexResponseError(
            f"Cortex response must be a dict, got {type(response).__name__}"
        )
    content = response.get("content", [])
    if not isinstance(content, list):
        raise CortexResponseError(
            f"Cortex response 'content' must be a list, got {type(content).__name__}"
        )
    return content


def extract_text_from_response(response: Dict[str, Any]) -> str:
    """
    Extract the concatenated text content from a Cortex response.

    Args:
        response: Parsed Cortex Messages response.

    Returns:
        All text blocks joined by a blank line, or an empty string if none.
    """
    text_parts = [
        block.get("text", "")
        for block in _content_blocks(response)
        if block.get("type") == CONTENT_TYPE_TEXT
    ]
    return TEXT_BLOCK_SEPARATOR.join(part for part in text_parts if part)


def extract_tool_uses(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract tool-call requests, keyed the way the existing agent loop expects.

    Anthropic names the identifier "id"; this remaps it to "toolUseId" so the
    three existing call sites are untouched by the Bedrock-to-Cortex port.

    Args:
        response: Parsed Cortex Messages response.

    Returns:
        One dict per tool call with toolUseId, name and input keys.
    """
    return [
        {
            TOOL_USE_ID_KEY: block.get("id"),
            "name": block.get("name"),
            "input": block.get("input", {}),
        }
        for block in _content_blocks(response)
        if block.get("type") == CONTENT_TYPE_TOOL_USE
    ]


def get_stop_reason(response: Dict[str, Any]) -> str:
    """
    Return the response stop reason.

    Args:
        response: Parsed Cortex Messages response.

    Returns:
        The stop_reason string, or an empty string when absent.
    """
    if not isinstance(response, dict):
        raise CortexResponseError(
            f"Cortex response must be a dict, got {type(response).__name__}"
        )
    return response.get("stop_reason") or ""


def extract_assistant_message(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the assistant turn to append to the conversation before replying.

    Under Bedrock the callers read response["output"]["message"] directly. That
    path does not exist in the Anthropic wire format, so this helper replaces it
    and returns the same {role, content} shape.

    Args:
        response: Parsed Cortex Messages response.

    Returns:
        An assistant message carrying the response's content blocks verbatim.
    """
    return {"role": ROLE_ASSISTANT, "content": _content_blocks(response)}


def format_tool_result(
    tool_use_id: str, result: Dict[str, Any], is_error: bool = False
) -> Dict[str, Any]:
    """
    Format a tool execution result as a user turn carrying a tool_result block.

    Args:
        tool_use_id: The id of the tool_use block being answered.
        result: The tool's return value, serialised to JSON text.
        is_error: Whether the tool raised. Defaults to False (success).

    Returns:
        A user message ready to append to the conversation.
    """
    return {
        "role": ROLE_USER,
        "content": [
            {
                "type": CONTENT_TYPE_TOOL_RESULT,
                "tool_use_id": tool_use_id,
                "content": json.dumps(result, default=str),
                "is_error": is_error,
            }
        ],
    }


def format_text_message(role: str, text: str) -> Dict[str, Any]:
    """
    Build a plain text turn in Anthropic block format.

    Bedrock accepts bare {"text": ...} blocks; Anthropic requires an explicit
    {"type": "text", "text": ...} discriminator. Callers that construct history
    by hand must route through this helper.

    Args:
        role: Either "user" or "assistant".
        text: The message text.

    Returns:
        A single-block message dictionary.
    """
    return {"role": role, "content": [{"type": CONTENT_TYPE_TEXT, "text": text}]}
