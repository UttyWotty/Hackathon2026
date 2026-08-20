"""Unit tests for the help_chat module's pure logic functions.

Validates system prompt content, message history management, and prompt building
without requiring a live Snowflake connection or Cortex API access.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Insert the frontend source directory so help_chat can be imported directly.
_FRONTEND_DIR = str(Path(__file__).resolve().parent.parent / "src" / "frontend")
if _FRONTEND_DIR not in sys.path:
    sys.path.insert(0, _FRONTEND_DIR)

# Mock heavy dependencies before importing help_chat.
sys.modules.setdefault("streamlit", MagicMock())
sys.modules.setdefault("snowflake.snowpark", MagicMock())
sys.modules.setdefault("snowflake.snowpark.context", MagicMock())
sys.modules.setdefault("session_helper", MagicMock())

import help_chat  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_session_state():
    """Reset the mocked session_state before each test."""
    help_chat.st.session_state = {}
    yield


class TestHelpSystemPrompt:
    """Tests for the static system prompt content."""

    def test_prompt_is_nonempty(self):
        """System prompt must contain substantial grounding text."""
        assert len(help_chat.HELP_SYSTEM_PROMPT) > 500

    def test_prompt_contains_architecture_keywords(self):
        """System prompt must reference the sense-reason-act architecture."""
        prompt = help_chat.HELP_SYSTEM_PROMPT
        assert "SENSE" in prompt
        assert "REASON" in prompt
        assert "ACT" in prompt
        assert "RECORD" in prompt

    def test_prompt_contains_data_model(self):
        """System prompt must reference core tables."""
        prompt = help_chat.HELP_SYSTEM_PROMPT
        assert "SHOT_DATA" in prompt
        assert "AUDIT_LOG" in prompt
        assert "SHIFT_NOTE" in prompt

    def test_prompt_contains_honesty_instruction(self):
        """System prompt must instruct the LLM to refuse hallucination."""
        prompt_lower = help_chat.HELP_SYSTEM_PROMPT.lower()
        assert "don't have that" in prompt_lower.replace("\n", " ")
        assert "information" in prompt_lower

    def test_prompt_contains_skills(self):
        """System prompt must reference the three CoCo skills."""
        prompt = help_chat.HELP_SYSTEM_PROMPT
        assert "$sense-equipment-anomalies" in prompt
        assert "$investigate-shift-notes" in prompt
        assert "$report-and-act" in prompt


class TestMessageHistory:
    """Tests for _append_message and history truncation."""

    def test_append_message_creates_list(self):
        """First append should create the session key."""
        help_chat._append_message("user", "hello")

        state = help_chat.st.session_state
        key = help_chat.HELP_CHAT_SESSION_KEY
        assert key in state
        assert len(state[key]) == 1
        assert state[key][0] == {"role": "user", "content": "hello"}

    def test_append_message_respects_max_history(self):
        """History should be truncated to HELP_CHAT_MAX_HISTORY."""
        key = help_chat.HELP_CHAT_SESSION_KEY
        help_chat.st.session_state = {key: []}

        for i in range(help_chat.HELP_CHAT_MAX_HISTORY + 5):
            help_chat._append_message("user", f"msg {i}")

        assert len(help_chat.st.session_state[key]) == help_chat.HELP_CHAT_MAX_HISTORY


class TestPromptBuilding:
    """Tests for _build_prompt_with_history."""

    def test_build_prompt_includes_system(self):
        """Built prompt must start with system prompt."""
        result = help_chat._build_prompt_with_history("What is this?")
        assert result.startswith(help_chat.HELP_SYSTEM_PROMPT)

    def test_build_prompt_includes_user_message(self):
        """Built prompt must include the new user message."""
        result = help_chat._build_prompt_with_history("What tabs exist?")
        assert "User: What tabs exist?" in result
        assert result.endswith("Assistant:")

    def test_build_prompt_includes_history(self):
        """Built prompt must include prior conversation turns."""
        key = help_chat.HELP_CHAT_SESSION_KEY
        help_chat.st.session_state = {
            key: [
                {"role": "user", "content": "first question"},
                {"role": "assistant", "content": "first answer"},
            ]
        }
        result = help_chat._build_prompt_with_history("follow up")

        assert "User: first question" in result
        assert "Assistant: first answer" in result
        assert "User: follow up" in result
