"""
Tests for the Cortex tool-definition adapter and the injectable client transport.

Verifies that all 35 registered tools convert from the Bedrock toolSpec shape to
the Anthropic input_schema shape without loss, and that CortexClient builds the
verified request headers and body. The client tests inject a fake transport, so
no network call or Snowflake account is involved.
"""

import json

import pytest

from core import cortex_client
from core.cortex_client import (
    ANTHROPIC_VERSION,
    TOKEN_TYPE_HEADER,
    TOKEN_TYPE_PAT,
    CortexClient,
)
from core.cortex_errors import (
    CortexConfigurationError,
    CortexRequestError,
    CortexResponseError,
)
from core.tools.cortex_adapter import convert_tool_to_cortex, get_tools_for_cortex
from core.tools.definitions import TOOLS

ACCOUNT = "myorg-myacct"
PAT = "test-token"
MODEL = "claude-sonnet-4-5"

STUB_RESPONSE = {
    "stop_reason": "end_turn",
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 5, "output_tokens": 7},
}


class RecordingTransport:
    """Fake transport capturing the last call and returning a canned response."""

    def __init__(self, response=None, error=None):
        self.response = response if response is not None else STUB_RESPONSE
        self.error = error
        self.url = None
        self.headers = None
        self.payload = None

    def __call__(self, url, headers, payload, timeout):
        self.url, self.headers, self.payload = url, headers, payload
        if self.error is not None:
            raise self.error
        return self.response


def _client(transport=None):
    """Build a client with credentials injected rather than read from the env."""
    return CortexClient(
        account=ACCOUNT,
        pat=PAT,
        model=MODEL,
        transport=transport or RecordingTransport(),
    )


class TestToolConversion:
    def test_every_registered_tool_converts(self):
        tools = get_tools_for_cortex()
        assert len(tools) == len(TOOLS)
        assert len(tools) > 0

    def test_converted_tools_have_anthropic_keys(self):
        for tool in get_tools_for_cortex():
            assert set(tool) == {"name", "description", "input_schema"}

    def test_tags_are_dropped(self):
        # tags exist for MCP and are rejected by the wire format.
        assert all("tags" not in tool for tool in get_tools_for_cortex())
        assert all(
            "tags" not in tool["input_schema"] for tool in get_tools_for_cortex()
        )

    def test_schema_is_unwrapped_from_the_json_envelope(self):
        source = {
            "toolSpec": {
                "name": "t",
                "description": "d",
                "inputSchema": {"json": {"type": "object", "properties": {"a": {}}}},
            }
        }
        converted = convert_tool_to_cortex(source)
        assert converted["input_schema"] == {"type": "object", "properties": {"a": {}}}

    def test_every_tool_name_is_preserved(self):
        source_names = {tool["toolSpec"]["name"] for tool in TOOLS}
        assert {tool["name"] for tool in get_tools_for_cortex()} == source_names

    def test_missing_schema_falls_back_to_empty_object(self):
        converted = convert_tool_to_cortex({"toolSpec": {"name": "t"}})
        assert converted["input_schema"]["type"] == "object"

    def test_missing_tool_spec_raises_domain_error(self):
        with pytest.raises(CortexResponseError):
            convert_tool_to_cortex({"nope": {}})

    def test_unnamed_tool_raises_domain_error(self):
        with pytest.raises(CortexResponseError):
            convert_tool_to_cortex({"toolSpec": {"description": "d"}})

    def test_all_tools_serialise_to_json(self):
        json.dumps(get_tools_for_cortex())


class TestClientConfiguration:
    def test_missing_account_raises(self, monkeypatch):
        # CortexClient falls back to os.getenv at construction time, so clear
        # the variable rather than patching a module attribute: a developer's
        # real .env must not mask this test.
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "")
        with pytest.raises(CortexConfigurationError):
            CortexClient(account=None, pat=PAT)

    def test_missing_pat_raises(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_PAT", "")
        with pytest.raises(CortexConfigurationError):
            CortexClient(account=ACCOUNT, pat=None)

    def test_account_falls_back_to_the_environment(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "env-account")
        assert CortexClient(account=None, pat=PAT).account == "env-account"

    def test_pat_falls_back_to_the_environment(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_PAT", "env-pat")
        assert CortexClient(account=ACCOUNT, pat=None).pat == "env-pat"

    def test_url_is_the_verified_messages_endpoint(self):
        assert (
            _client().url
            == "https://myorg-myacct.snowflakecomputing.com/api/v2/cortex/v1/messages"
        )


class TestClientRequest:
    def test_headers_match_the_verified_shape(self):
        transport = RecordingTransport()
        _client(transport).get_response([{"role": "user", "content": "hi"}])
        assert transport.headers["Authorization"] == f"Bearer {PAT}"
        assert transport.headers["anthropic-version"] == ANTHROPIC_VERSION
        assert transport.headers[TOKEN_TYPE_HEADER] == TOKEN_TYPE_PAT

    def test_pat_is_not_leaked_into_the_payload(self):
        transport = RecordingTransport()
        _client(transport).get_response([{"role": "user", "content": "hi"}])
        assert PAT not in json.dumps(transport.payload)

    def test_payload_carries_model_and_messages(self):
        transport = RecordingTransport()
        messages = [{"role": "user", "content": "hi"}]
        _client(transport).get_response(messages)
        assert transport.payload["model"] == MODEL
        assert transport.payload["messages"] == messages

    def test_tools_are_forwarded(self):
        transport = RecordingTransport()
        _client(transport).get_response(
            [{"role": "user", "content": "hi"}], tools=get_tools_for_cortex()
        )
        assert len(transport.payload["tools"]) == len(TOOLS)

    def test_response_is_returned_unwrapped(self):
        assert (
            _client().get_response([{"role": "user", "content": "hi"}]) == STUB_RESPONSE
        )

    def test_transport_failure_returns_none(self):
        # Matches BedrockClient: callers check `if not response`.
        transport = RecordingTransport(error=CortexRequestError("boom"))
        assert (
            _client(transport).get_response([{"role": "user", "content": "hi"}]) is None
        )

    def test_missing_usage_does_not_break_the_call(self):
        transport = RecordingTransport(
            response={"content": [], "stop_reason": "end_turn"}
        )
        assert (
            _client(transport).get_response([{"role": "user", "content": "hi"}])
            is not None
        )
