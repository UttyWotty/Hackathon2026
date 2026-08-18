"""
Pure translation between the Anthropic wire format and the OpenAI chat format.

Lets a local mlx_lm.server stand in for Cortex during development by converting
requests down to OpenAI shape and lifting responses back into Anthropic shape,
so cortex_wire's parsers and the agent loop stay backend-agnostic. This module
performs no I/O and is fully testable offline.
"""

import json
from typing import Any, Dict, List, Optional

from .cortex_errors import CortexResponseError
from .cortex_wire import (
    CONTENT_TYPE_TEXT,
    CONTENT_TYPE_TOOL_RESULT,
    CONTENT_TYPE_TOOL_USE,
    ROLE_ASSISTANT,
    ROLE_USER,
)

# OpenAI roles and discriminators.
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"
FUNCTION_TYPE = "function"

# finish_reason to stop_reason. OpenAI's "tool_calls" is the loop's "tool_use";
# every other terminal reason maps to a non-tool value so the loop exits.
FINISH_REASON_MAP = {
    "tool_calls": "tool_use",
    "stop": "end_turn",
    "length": "max_tokens",
    "content_filter": "stop_sequence",
}
DEFAULT_STOP_REASON = "end_turn"


def convert_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Anthropic tool definitions to OpenAI function definitions.

    Args:
        tools: Tools in Anthropic format (name, description, input_schema).

    Returns:
        The same tools wrapped in OpenAI's function envelope.
    """
    return [
        {
            "type": FUNCTION_TYPE,
            FUNCTION_TYPE: {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }
        for tool in tools
    ]


def _blocks_of_type(content: Any, block_type: str) -> List[Dict[str, Any]]:
    """Return content blocks of one type, tolerating a bare string content."""
    if not isinstance(content, list):
        return []
    return [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == block_type
    ]


def _text_of(content: Any) -> str:
    """Flatten a message's content down to plain text."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in _blocks_of_type(content, CONTENT_TYPE_TEXT)
    )


def _convert_assistant_turn(content: Any) -> Dict[str, Any]:
    """Convert one Anthropic assistant turn, carrying any tool calls across."""
    message: Dict[str, Any] = {
        "role": ROLE_ASSISTANT,
        "content": _text_of(content) or None,
    }
    tool_uses = _blocks_of_type(content, CONTENT_TYPE_TOOL_USE)
    if tool_uses:
        message["tool_calls"] = [
            {
                "id": block.get("id"),
                "type": FUNCTION_TYPE,
                FUNCTION_TYPE: {
                    "name": block.get("name"),
                    "arguments": json.dumps(block.get("input", {})),
                },
            }
            for block in tool_uses
        ]
    return message


def convert_messages_to_openai(
    messages: List[Dict[str, Any]], system_prompt: str
) -> List[Dict[str, Any]]:
    """
    Convert an Anthropic conversation to OpenAI messages.

    Anthropic carries tool results as blocks inside a user turn; OpenAI requires
    each to be its own message with role "tool", so one turn can fan out to many.

    Args:
        messages: Conversation turns in Anthropic format.
        system_prompt: System prompt, emitted as the leading system message.

    Returns:
        The conversation in OpenAI format.
    """
    converted: List[Dict[str, Any]] = [{"role": ROLE_SYSTEM, "content": system_prompt}]

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == ROLE_ASSISTANT:
            converted.append(_convert_assistant_turn(content))
            continue

        tool_results = _blocks_of_type(content, CONTENT_TYPE_TOOL_RESULT)
        if tool_results:
            converted.extend(
                {
                    "role": ROLE_TOOL,
                    "tool_call_id": block.get("tool_use_id"),
                    "content": block.get("content", ""),
                }
                for block in tool_results
            )
            continue

        converted.append({"role": ROLE_USER, "content": _text_of(content)})

    return converted


def build_openai_payload(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    tools: Optional[List[Dict[str, Any]]],
    model: str,
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    """
    Build the request body for POST /v1/chat/completions.

    Args:
        messages: Conversation turns in Anthropic format.
        system_prompt: System prompt text.
        tools: Anthropic-format tools, or None to omit the key.
        model: Model name as served by mlx_lm.server.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.

    Returns:
        The request body as a plain dictionary.
    """
    payload: Dict[str, Any] = {
        "model": model,
        "messages": convert_messages_to_openai(messages, system_prompt),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = convert_tools_to_openai(tools)
    return payload


def _parse_arguments(raw: Any) -> Dict[str, Any]:
    """Parse a tool call's JSON argument string, tolerating an empty value."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise CortexResponseError(
            f"Local model emitted non-JSON tool arguments: {raw!r}"
        ) from exc


def convert_response_to_anthropic(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lift an OpenAI chat completion into the Anthropic response shape.

    The result is consumed by cortex_wire's parsers unchanged, which is what
    keeps the agent loop identical across the two backends.

    Args:
        response: Parsed /v1/chat/completions response.

    Returns:
        A dict with content, stop_reason and usage in Anthropic shape.

    Raises:
        CortexResponseError: If the payload carries no choices.
    """
    choices = response.get("choices") if isinstance(response, dict) else None
    if not choices:
        raise CortexResponseError(f"Local model returned no choices: {response!r}")

    choice = choices[0]
    message = choice.get("message", {})
    content: List[Dict[str, Any]] = []

    text = message.get("content")
    if text:
        content.append({"type": CONTENT_TYPE_TEXT, "text": text})

    for call in message.get("tool_calls") or []:
        function = call.get(FUNCTION_TYPE, {})
        content.append(
            {
                "type": CONTENT_TYPE_TOOL_USE,
                "id": call.get("id"),
                "name": function.get("name"),
                "input": _parse_arguments(function.get("arguments")),
            }
        )

    usage = response.get("usage", {})
    return {
        "content": content,
        "stop_reason": FINISH_REASON_MAP.get(
            choice.get("finish_reason"), DEFAULT_STOP_REASON
        ),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }
