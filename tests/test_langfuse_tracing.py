"""
Unit tests for the observability tracing wrappers.

Tests TracedMlxLLMService and TracedBedrockClient proxy behavior,
Langfuse client factory logic, and graceful degradation when Langfuse
is disabled or unavailable.
"""

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from services.infrastructure.ml.mlx_llm import ChatResponse

# ---------------------------------------------------------------------------
# Langfuse client factory
# ---------------------------------------------------------------------------


class TestLangfuseClient:
    """Tests for the Langfuse client singleton factory."""

    @patch.dict(
        "os.environ",
        {
            "LANGFUSE_ENABLED": "False",
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
        },
    )
    def test_disabled_returns_none(self) -> None:
        import services.infrastructure.observability.langfuse_client as mod

        mod._initialized = False
        mod._langfuse_instance = None
        mod.LANGFUSE_ENABLED = False

        result = mod.get_langfuse()
        assert result is None

    @patch.dict(
        "os.environ",
        {
            "LANGFUSE_ENABLED": "True",
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        },
    )
    def test_missing_keys_returns_none(self) -> None:
        import services.infrastructure.observability.langfuse_client as mod

        mod._initialized = False
        mod._langfuse_instance = None
        mod.LANGFUSE_ENABLED = True
        mod.LANGFUSE_PUBLIC_KEY = ""
        mod.LANGFUSE_SECRET_KEY = ""

        result = mod.get_langfuse()
        assert result is None

    def test_shutdown_clears_singleton(self) -> None:
        import services.infrastructure.observability.langfuse_client as mod

        mock_client = MagicMock()
        mod._langfuse_instance = mock_client
        mod._initialized = True

        mod.shutdown_langfuse()

        mock_client.flush.assert_called_once()
        mock_client.shutdown.assert_called_once()
        assert mod._langfuse_instance is None
        assert mod._initialized is False

    def test_shutdown_when_not_initialized(self) -> None:
        import services.infrastructure.observability.langfuse_client as mod

        mod._langfuse_instance = None
        mod._initialized = False

        mod.shutdown_langfuse()
        assert mod._initialized is False


# ---------------------------------------------------------------------------
# TracedMlxLLMService
# ---------------------------------------------------------------------------


class TestTracedMlxLLMService:
    """Tests for the MLX tracing proxy."""

    def _make_response(self) -> ChatResponse:
        return ChatResponse(
            content="Test response",
            model="test-model",
            finish_reason="stop",
            total_duration_ms=100.0,
            prompt_eval_count=50,
            eval_count=30,
        )

    def _make_inner_mock(self) -> MagicMock:
        inner = MagicMock()
        inner.host = "http://127.0.0.1:8080"
        inner.default_model = "test-model"
        inner.chat.return_value = self._make_response()
        inner.generate_sql.return_value = "SELECT 1"
        inner.analyze.return_value = "Analysis result"
        inner.quick_response.return_value = "Quick answer"
        return inner

    @patch(
        "services.infrastructure.observability.trace_mlx.get_langfuse",
        return_value=None,
    )
    def test_chat_passthrough_when_disabled(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        inner = self._make_inner_mock()
        traced = TracedMlxLLMService(inner)

        messages = [{"role": "user", "content": "Hello"}]
        result = traced.chat(messages)

        inner.chat.assert_called_once()
        assert result.content == "Test response"

    @patch("services.infrastructure.observability.trace_mlx.get_langfuse")
    def test_chat_with_tracing(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation
        mock_get.return_value = mock_langfuse

        inner = self._make_inner_mock()
        traced = TracedMlxLLMService(inner)

        messages = [{"role": "user", "content": "Hello"}]
        result = traced.chat(messages)

        inner.chat.assert_called_once()
        mock_langfuse.trace.assert_called_once()
        mock_trace.generation.assert_called_once()
        mock_generation.end.assert_called_once()
        assert result.content == "Test response"

    @patch("services.infrastructure.observability.trace_mlx.get_langfuse")
    def test_chat_error_still_traces(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation
        mock_get.return_value = mock_langfuse

        inner = self._make_inner_mock()
        inner.chat.side_effect = RuntimeError("Server down")
        traced = TracedMlxLLMService(inner)

        with pytest.raises(RuntimeError, match="Server down"):
            traced.chat([{"role": "user", "content": "Hello"}])

        mock_generation.end.assert_called_once()
        call_kwargs = mock_generation.end.call_args
        assert call_kwargs[1]["level"] == "ERROR"

    @patch(
        "services.infrastructure.observability.trace_mlx.get_langfuse",
        return_value=None,
    )
    def test_generate_sql_passthrough(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        inner = self._make_inner_mock()
        traced = TracedMlxLLMService(inner)

        result = traced.generate_sql("Get all equipment")
        assert result == "SELECT 1"
        inner.generate_sql.assert_called_once()

    @patch(
        "services.infrastructure.observability.trace_mlx.get_langfuse",
        return_value=None,
    )
    def test_analyze_passthrough(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        inner = self._make_inner_mock()
        traced = TracedMlxLLMService(inner)

        result = traced.analyze("data here", "what is the trend?")
        assert result == "Analysis result"

    @patch(
        "services.infrastructure.observability.trace_mlx.get_langfuse",
        return_value=None,
    )
    def test_quick_response_passthrough(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        inner = self._make_inner_mock()
        traced = TracedMlxLLMService(inner)

        result = traced.quick_response("Hi")
        assert result == "Quick answer"

    @patch(
        "services.infrastructure.observability.trace_mlx.get_langfuse",
        return_value=None,
    )
    def test_attribute_delegation(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        inner = self._make_inner_mock()
        traced = TracedMlxLLMService(inner)

        assert traced.host == "http://127.0.0.1:8080"
        assert traced.default_model == "test-model"

    @patch(
        "services.infrastructure.observability.trace_mlx.get_langfuse",
        return_value=None,
    )
    def test_chat_stream_passthrough(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_mlx import TracedMlxLLMService

        inner = self._make_inner_mock()
        inner.chat_stream.return_value = iter(["Hello", " world"])
        traced = TracedMlxLLMService(inner)

        tokens = list(traced.chat_stream([{"role": "user", "content": "Hi"}]))
        assert tokens == ["Hello", " world"]


# ---------------------------------------------------------------------------
# TracedBedrockClient
# ---------------------------------------------------------------------------


class TestTracedBedrockClient:
    """Tests for the Bedrock tracing proxy."""

    def _make_bedrock_response(self) -> Dict[str, Any]:
        return {
            "output": {
                "message": {
                    "content": [{"text": "Test Bedrock response"}],
                    "role": "assistant",
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 100, "outputTokens": 50},
        }

    @patch(
        "services.infrastructure.observability.trace_bedrock.get_langfuse",
        return_value=None,
    )
    def test_passthrough_when_disabled(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_bedrock import (
            TracedBedrockClient,
        )

        inner = MagicMock()
        inner.model_id = "anthropic.claude-3-5-sonnet"
        inner.get_response.return_value = self._make_bedrock_response()
        traced = TracedBedrockClient(inner)

        result = traced.get_response(
            messages=[{"role": "user", "content": [{"text": "Hi"}]}],
        )

        inner.get_response.assert_called_once()
        assert result is not None

    @patch("services.infrastructure.observability.trace_bedrock.get_langfuse")
    def test_with_tracing(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_bedrock import (
            TracedBedrockClient,
        )

        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation
        mock_get.return_value = mock_langfuse

        inner = MagicMock()
        inner.model_id = "anthropic.claude-3-5-sonnet"
        inner.get_response.return_value = self._make_bedrock_response()
        traced = TracedBedrockClient(inner)

        result = traced.get_response(
            messages=[{"role": "user", "content": [{"text": "Hi"}]}],
        )

        mock_langfuse.trace.assert_called_once()
        mock_generation.end.assert_called_once()
        assert result is not None

    @patch("services.infrastructure.observability.trace_bedrock.get_langfuse")
    def test_none_response_traced(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_bedrock import (
            TracedBedrockClient,
        )

        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation
        mock_get.return_value = mock_langfuse

        inner = MagicMock()
        inner.model_id = "anthropic.claude-3-5-sonnet"
        inner.get_response.return_value = None
        traced = TracedBedrockClient(inner)

        result = traced.get_response(
            messages=[{"role": "user", "content": [{"text": "Hi"}]}],
        )

        assert result is None
        mock_generation.end.assert_called_once()
        call_kwargs = mock_generation.end.call_args[1]
        assert call_kwargs["level"] == "WARNING"

    @patch(
        "services.infrastructure.observability.trace_bedrock.get_langfuse",
        return_value=None,
    )
    def test_attribute_delegation(self, mock_get: MagicMock) -> None:
        from services.infrastructure.observability.trace_bedrock import (
            TracedBedrockClient,
        )

        inner = MagicMock()
        inner.model_id = "anthropic.claude-3-5-sonnet"
        inner.bedrock = "bedrock-runtime-client"
        traced = TracedBedrockClient(inner)

        assert traced.model_id == "anthropic.claude-3-5-sonnet"
        assert traced.bedrock == "bedrock-runtime-client"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for trace helper functions."""

    def test_extract_last_user_message_dict(self) -> None:
        from services.infrastructure.observability.trace_mlx import (
            _extract_last_user_message,
        )

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "Answer"},
            {"role": "user", "content": "Second question"},
        ]
        result = _extract_last_user_message(messages)
        assert result == "Second question"

    def test_extract_last_user_message_empty(self) -> None:
        from services.infrastructure.observability.trace_mlx import (
            _extract_last_user_message,
        )

        result = _extract_last_user_message([])
        assert result == ""

    def test_extract_bedrock_input(self) -> None:
        from services.infrastructure.observability.trace_bedrock import (
            _extract_bedrock_input,
        )

        messages = [
            {"role": "user", "content": [{"text": "Hello from Bedrock"}]},
        ]
        result = _extract_bedrock_input(messages)
        assert result == "Hello from Bedrock"

    def test_extract_bedrock_output(self) -> None:
        from services.infrastructure.observability.trace_bedrock import (
            _extract_bedrock_output,
        )

        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "Part 1"},
                        {"text": "Part 2"},
                    ]
                }
            }
        }
        result = _extract_bedrock_output(response)
        assert "Part 1" in result
        assert "Part 2" in result
