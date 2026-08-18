"""
Tests for the pure Cortex request-building and response-parsing helpers.

Asserts the parser contracts the existing agent loop depends on, in particular
the Anthropic "id" to "toolUseId" remap that lets the three call sites survive
the Bedrock-to-Cortex port untouched. No network, no account, no mocks.
"""

import json

import pytest

from core.cortex_errors import CortexResponseError
from core.cortex_wire import (
    CACHE_CONTROL_EPHEMERAL,
    STOP_REASON_TOOL_USE,
    build_messages_payload,
    extract_assistant_message,
    extract_text_from_response,
    extract_tool_uses,
    format_text_message,
    format_tool_result,
    get_stop_reason,
)

SYSTEM_PROMPT = "You are a manufacturing analyst."
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024
TEMPERATURE = 0.7

TOOL_USE_RESPONSE = {
    "stop_reason": "tool_use",
    "content": [
        {"type": "text", "text": "Checking the deviation."},
        {
            "type": "tool_use",
            "id": "toolu_abc123",
            "name": "run_deviation_analysis",
            "input": {"machine": "MX-7103"},
        },
    ],
    "usage": {"input_tokens": 10, "output_tokens": 20},
}

TEXT_RESPONSE = {
    "stop_reason": "end_turn",
    "content": [{"type": "text", "text": "First"}, {"type": "text", "text": "Second"}],
}


def _payload(tools=None, caching=True):
    """Build a payload with the fixture defaults."""
    return build_messages_payload(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        enable_prompt_caching=caching,
    )


class TestBuildMessagesPayload:
    def test_required_fields_present(self):
        payload = _payload()
        assert payload["model"] == MODEL
        assert payload["max_tokens"] == MAX_TOKENS
        assert payload["temperature"] == TEMPERATURE
        assert payload["messages"] == [{"role": "user", "content": "hi"}]

    def test_system_is_a_block_list_not_a_string(self):
        # Anthropic accepts a bare string, but a block list is required to carry
        # the cache_control breakpoint.
        payload = _payload()
        assert isinstance(payload["system"], list)
        assert payload["system"][0]["text"] == SYSTEM_PROMPT

    def test_prompt_caching_adds_ephemeral_breakpoint(self):
        payload = _payload(caching=True)
        assert payload["system"][0]["cache_control"] == {
            "type": CACHE_CONTROL_EPHEMERAL
        }

    def test_prompt_caching_can_be_disabled(self):
        payload = _payload(caching=False)
        assert "cache_control" not in payload["system"][0]

    def test_tools_key_omitted_when_absent(self):
        assert "tools" not in _payload(tools=None)
        assert "tools" not in _payload(tools=[])

    def test_tools_passed_through(self):
        tools = [{"name": "t", "description": "", "input_schema": {}}]
        assert _payload(tools=tools)["tools"] == tools

    def test_payload_is_json_serialisable(self):
        json.dumps(_payload(tools=[{"name": "t"}]))


class TestExtractToolUses:
    def test_remaps_anthropic_id_to_tool_use_id(self):
        # The crux of the port: call sites read tool_use.get("toolUseId").
        uses = extract_tool_uses(TOOL_USE_RESPONSE)
        assert len(uses) == 1
        assert uses[0]["toolUseId"] == "toolu_abc123"
        assert "id" not in uses[0]

    def test_carries_name_and_input(self):
        use = extract_tool_uses(TOOL_USE_RESPONSE)[0]
        assert use["name"] == "run_deviation_analysis"
        assert use["input"] == {"machine": "MX-7103"}

    def test_ignores_text_blocks(self):
        assert extract_tool_uses(TEXT_RESPONSE) == []

    def test_missing_input_defaults_to_empty_dict(self):
        response = {"content": [{"type": "tool_use", "id": "x", "name": "n"}]}
        assert extract_tool_uses(response)[0]["input"] == {}


class TestExtractText:
    def test_joins_blocks_with_blank_line(self):
        assert extract_text_from_response(TEXT_RESPONSE) == "First\n\nSecond"

    def test_skips_tool_use_blocks(self):
        assert (
            extract_text_from_response(TOOL_USE_RESPONSE) == "Checking the deviation."
        )

    def test_empty_content_returns_empty_string(self):
        assert extract_text_from_response({"content": []}) == ""

    def test_missing_content_returns_empty_string(self):
        assert extract_text_from_response({}) == ""


class TestGetStopReason:
    def test_tool_use_sentinel_matches_the_loop_comparison(self):
        # The loop compares against the literal "tool_use"; Bedrock and Cortex
        # agree on this string, so the comparison survives the port.
        assert get_stop_reason(TOOL_USE_RESPONSE) == STOP_REASON_TOOL_USE

    def test_end_turn(self):
        assert get_stop_reason(TEXT_RESPONSE) == "end_turn"

    def test_missing_returns_empty_string(self):
        assert get_stop_reason({}) == ""

    def test_null_stop_reason_returns_empty_string(self):
        assert get_stop_reason({"stop_reason": None}) == ""


class TestExtractAssistantMessage:
    def test_replaces_the_bedrock_output_message_path(self):
        message = extract_assistant_message(TOOL_USE_RESPONSE)
        assert message["role"] == "assistant"
        assert message["content"] == TOOL_USE_RESPONSE["content"]

    def test_round_trips_into_a_follow_up_request(self):
        # The assistant turn must be appendable to messages and re-sendable.
        message = extract_assistant_message(TOOL_USE_RESPONSE)
        payload = build_messages_payload(
            messages=[{"role": "user", "content": "hi"}, message],
            system_prompt=SYSTEM_PROMPT,
            tools=None,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            enable_prompt_caching=True,
        )
        json.dumps(payload)
        assert payload["messages"][1]["role"] == "assistant"


class TestFormatToolResult:
    def test_success_shape(self):
        message = format_tool_result("toolu_abc123", {"rows": 3})
        block = message["content"][0]
        assert message["role"] == "user"
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_abc123"
        assert block["is_error"] is False
        assert json.loads(block["content"]) == {"rows": 3}

    def test_error_flag_set(self):
        message = format_tool_result("t1", {"error": "boom"}, is_error=True)
        assert message["content"][0]["is_error"] is True

    def test_non_serialisable_values_do_not_raise(self):
        # Tool results carry datetimes and Decimals; default=str must absorb them.
        from datetime import datetime

        message = format_tool_result("t1", {"at": datetime(2026, 7, 21)})
        assert "2026-07-21" in message["content"][0]["content"]

    def test_tool_use_id_matches_extract_tool_uses_output(self):
        # End-to-end id continuity: what we extract is what we must reply with.
        use = extract_tool_uses(TOOL_USE_RESPONSE)[0]
        message = format_tool_result(use["toolUseId"], {"ok": True})
        assert message["content"][0]["tool_use_id"] == "toolu_abc123"


class TestFormatTextMessage:
    def test_uses_anthropic_type_discriminator(self):
        # Bedrock accepted a bare {"text": ...} block; Anthropic does not.
        message = format_text_message("user", "hello")
        assert message["content"][0] == {"type": "text", "text": "hello"}


class TestMalformedResponses:
    def test_non_dict_response_raises_domain_error(self):
        with pytest.raises(CortexResponseError):
            extract_text_from_response("not a dict")

    def test_non_list_content_raises_domain_error(self):
        with pytest.raises(CortexResponseError):
            extract_tool_uses({"content": "oops"})

    def test_non_dict_stop_reason_raises_domain_error(self):
        with pytest.raises(CortexResponseError):
            get_stop_reason(None)
