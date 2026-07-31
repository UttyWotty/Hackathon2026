"""
Tests for the MLX OpenAI-format translation and the backend factory.

Asserts the round trip that makes the two backends interchangeable: an OpenAI
chat completion lifted into Anthropic shape must parse with cortex_wire's
helpers exactly as a real Cortex response does. No network and no local model.
"""

import json

import pytest

from core.cortex_errors import CortexConfigurationError, CortexResponseError
from core.cortex_wire import (
    extract_text_from_response,
    extract_tool_uses,
    get_stop_reason,
)
from core.llm_backend import BACKEND_CORTEX, BACKEND_MLX, get_llm_client
from core.mlx_wire import (
    build_openai_payload,
    convert_messages_to_openai,
    convert_response_to_anthropic,
    convert_tools_to_openai,
)

SYSTEM_PROMPT = "You are a manufacturing analyst."
MODEL = "mlx-community/Qwen3-32B-4bit"

ANTHROPIC_TOOLS = [
    {
        "name": "run_ct_deviation_analysis",
        "description": "Analyse cycle time deviation.",
        "input_schema": {
            "type": "object",
            "properties": {"machine": {"type": "string"}},
        },
    }
]

OPENAI_TOOL_CALL_RESPONSE = {
    "choices": [
        {
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": "Checking.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "run_ct_deviation_analysis",
                            "arguments": '{"machine": "MX-7103"}',
                        },
                    }
                ],
            },
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 22},
}

OPENAI_TEXT_RESPONSE = {
    "choices": [{"finish_reason": "stop", "message": {"content": "All healthy."}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 4},
}


class TestToolConversion:
    def test_input_schema_becomes_parameters(self):
        converted = convert_tools_to_openai(ANTHROPIC_TOOLS)[0]
        assert converted["type"] == "function"
        assert converted["function"]["parameters"] == ANTHROPIC_TOOLS[0]["input_schema"]

    def test_name_and_description_preserved(self):
        function = convert_tools_to_openai(ANTHROPIC_TOOLS)[0]["function"]
        assert function["name"] == "run_ct_deviation_analysis"
        assert function["description"] == "Analyse cycle time deviation."


class TestMessageConversion:
    def test_system_prompt_leads_the_conversation(self):
        converted = convert_messages_to_openai([], SYSTEM_PROMPT)
        assert converted[0] == {"role": "system", "content": SYSTEM_PROMPT}

    def test_plain_user_text(self):
        converted = convert_messages_to_openai(
            [{"role": "user", "content": "hi"}], SYSTEM_PROMPT
        )
        assert converted[1] == {"role": "user", "content": "hi"}

    def test_user_text_blocks_are_flattened(self):
        converted = convert_messages_to_openai(
            [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            SYSTEM_PROMPT,
        )
        assert converted[1]["content"] == "hi"

    def test_assistant_tool_use_becomes_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "t",
                        "input": {"a": 1},
                    }
                ],
            }
        ]
        call = convert_messages_to_openai(messages, SYSTEM_PROMPT)[1]["tool_calls"][0]
        assert call["id"] == "call_1"
        assert json.loads(call["function"]["arguments"]) == {"a": 1}

    def test_tool_result_becomes_its_own_tool_message(self):
        # Anthropic nests results in a user turn; OpenAI needs separate messages.
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": '{"rows": 3}',
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_2",
                        "content": '{"rows": 4}',
                    },
                ],
            }
        ]
        converted = convert_messages_to_openai(messages, SYSTEM_PROMPT)
        assert [m["role"] for m in converted[1:]] == ["tool", "tool"]
        assert converted[1]["tool_call_id"] == "call_1"
        assert converted[2]["tool_call_id"] == "call_2"

    def test_payload_is_json_serialisable(self):
        payload = build_openai_payload(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt=SYSTEM_PROMPT,
            tools=ANTHROPIC_TOOLS,
            model=MODEL,
            max_tokens=100,
            temperature=0.7,
        )
        json.dumps(payload)
        assert payload["model"] == MODEL

    def test_tools_omitted_when_absent(self):
        payload = build_openai_payload(
            messages=[],
            system_prompt=SYSTEM_PROMPT,
            tools=None,
            model=MODEL,
            max_tokens=100,
            temperature=0.7,
        )
        assert "tools" not in payload


class TestResponseConversion:
    def test_finish_reason_tool_calls_maps_to_the_loop_sentinel(self):
        # The whole point: the loop compares stop_reason against "tool_use".
        converted = convert_response_to_anthropic(OPENAI_TOOL_CALL_RESPONSE)
        assert get_stop_reason(converted) == "tool_use"

    def test_stop_maps_to_end_turn(self):
        converted = convert_response_to_anthropic(OPENAI_TEXT_RESPONSE)
        assert get_stop_reason(converted) == "end_turn"

    def test_unknown_finish_reason_does_not_loop_forever(self):
        response = {
            "choices": [{"finish_reason": "weird", "message": {"content": "x"}}]
        }
        assert get_stop_reason(convert_response_to_anthropic(response)) != "tool_use"

    def test_converted_response_parses_with_cortex_helpers(self):
        # Backend interchangeability, asserted end to end.
        converted = convert_response_to_anthropic(OPENAI_TOOL_CALL_RESPONSE)
        assert extract_text_from_response(converted) == "Checking."
        uses = extract_tool_uses(converted)
        assert uses[0]["toolUseId"] == "call_1"
        assert uses[0]["name"] == "run_ct_deviation_analysis"
        assert uses[0]["input"] == {"machine": "MX-7103"}

    def test_usage_is_remapped(self):
        converted = convert_response_to_anthropic(OPENAI_TOOL_CALL_RESPONSE)
        assert converted["usage"] == {"input_tokens": 11, "output_tokens": 22}

    def test_missing_usage_defaults_to_zero(self):
        converted = convert_response_to_anthropic(
            {"choices": [{"finish_reason": "stop", "message": {"content": "x"}}]}
        )
        assert converted["usage"] == {"input_tokens": 0, "output_tokens": 0}

    def test_empty_choices_raises_domain_error(self):
        with pytest.raises(CortexResponseError):
            convert_response_to_anthropic({"choices": []})

    def test_malformed_tool_arguments_raise_domain_error(self):
        # Small local models emit invalid JSON arguments; fail loudly, not silently.
        response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {"name": "t", "arguments": "{not json"},
                            }
                        ]
                    },
                }
            ]
        }
        with pytest.raises(CortexResponseError):
            convert_response_to_anthropic(response)

    def test_text_only_response_has_no_tool_uses(self):
        converted = convert_response_to_anthropic(OPENAI_TEXT_RESPONSE)
        assert extract_tool_uses(converted) == []
        assert extract_text_from_response(converted) == "All healthy."


class TestBackendFactory:
    def test_default_backend_is_cortex_when_env_is_unset(self, monkeypatch):
        # Reloaded under a cleared env so a developer's local LLM_BACKEND=mlx
        # in .env cannot make this pass or fail spuriously.
        import importlib

        import core.llm_backend as backend_module

        monkeypatch.delenv("LLM_BACKEND", raising=False)
        reloaded = importlib.reload(backend_module)
        try:
            assert reloaded.LLM_BACKEND == BACKEND_CORTEX
        finally:
            importlib.reload(backend_module)

    def test_unknown_backend_raises(self):
        with pytest.raises(CortexConfigurationError):
            get_llm_client("gpt4all")

    def test_mlx_backend_builds_without_credentials(self):
        # The point of the dev backend: no account, no PAT, no network at init.
        client = get_llm_client(BACKEND_MLX)
        assert client.url.endswith("/v1/chat/completions")

    def test_cortex_backend_never_silently_falls_back_to_local(self):
        # Whether credentials are present or not, asking for cortex must never
        # hand back a local client. Misconfiguration must be loud.
        from core.mlx_client import MLXClient

        try:
            client = get_llm_client(BACKEND_CORTEX)
        except CortexConfigurationError:
            return
        assert not isinstance(client, MLXClient)
