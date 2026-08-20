"""Unit tests for action_loop pure logic: validation, escaping, severity.

Tests the input validation and SQL escaping functions without requiring
a live Snowflake connection. Also tests severity classification from
interactive_controls.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_FRONTEND_DIR = str(Path(__file__).resolve().parent.parent / "src" / "frontend")
if _FRONTEND_DIR not in sys.path:
    sys.path.insert(0, _FRONTEND_DIR)

sys.modules.setdefault("streamlit", MagicMock())
sys.modules.setdefault("snowflake.snowpark", MagicMock())
sys.modules.setdefault("snowflake.snowpark.context", MagicMock())
sys.modules.setdefault("session_helper", MagicMock())

import action_loop  # noqa: E402
import interactive_controls  # noqa: E402


class TestValidateMachineId:
    """Tests for _validate_machine_id."""

    def test_valid_id(self):
        """Standard MX-NNNN format passes."""
        assert action_loop._validate_machine_id("MX-7103") == "MX-7103"

    def test_lowercase_normalized(self):
        """Lowercase input is uppercased."""
        assert action_loop._validate_machine_id("mx-7103") == "MX-7103"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        assert action_loop._validate_machine_id("  MX-9201  ") == "MX-9201"

    def test_invalid_format_raises(self):
        """Non-matching format raises ValueError."""
        with pytest.raises(ValueError):
            action_loop._validate_machine_id("INVALID")

    def test_injection_attempt_raises(self):
        """SQL injection in machine ID raises ValueError."""
        with pytest.raises(ValueError):
            action_loop._validate_machine_id("MX-7103'; DROP TABLE --")

    def test_empty_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError):
            action_loop._validate_machine_id("")


class TestEscapeSqlStr:
    """Tests for _escape_sql_str."""

    def test_single_quote(self):
        """Single quotes are doubled."""
        assert action_loop._escape_sql_str("it's") == "it''s"

    def test_backslash(self):
        """Backslashes are doubled."""
        assert action_loop._escape_sql_str("path\\to") == "path\\\\to"

    def test_both(self):
        """Both backslash and quote are handled."""
        assert action_loop._escape_sql_str("it's a\\path") == "it''s a\\\\path"

    def test_clean_string(self):
        """String without special chars passes through."""
        assert action_loop._escape_sql_str("hello world") == "hello world"


class TestClassifySeverity:
    """Tests for classify_severity."""

    def test_critical(self):
        """Deviation >= 15% is CRITICAL."""
        assert interactive_controls.classify_severity(15.0) == "CRITICAL"
        assert interactive_controls.classify_severity(20.0) == "CRITICAL"

    def test_warning(self):
        """Deviation >= 10% but < 15% is WARNING."""
        assert interactive_controls.classify_severity(10.0) == "WARNING"
        assert interactive_controls.classify_severity(12.5) == "WARNING"

    def test_minor(self):
        """Deviation >= 5% but < 10% is MINOR."""
        assert interactive_controls.classify_severity(5.0) == "MINOR"
        assert interactive_controls.classify_severity(7.5) == "MINOR"

    def test_nominal(self):
        """Deviation < 5% is NOMINAL."""
        assert interactive_controls.classify_severity(4.9) == "NOMINAL"
        assert interactive_controls.classify_severity(0.0) == "NOMINAL"

    def test_negative_deviation(self):
        """Negative deviation uses absolute value."""
        assert interactive_controls.classify_severity(-15.0) == "CRITICAL"
        assert interactive_controls.classify_severity(-10.0) == "WARNING"
