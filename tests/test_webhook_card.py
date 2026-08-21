"""Tests for webhook payload parsing in src/frontend/action_loop.py.

Covers the round trip from _build_webhook_payload to _parse_payload, and the
domain error raised for payloads that do not match the Cards v2 shape.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("streamlit", MagicMock())

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

import action_loop  # noqa: E402


def _payload():
    return action_loop._build_webhook_payload(
        "MX-7103", "WARNING", "[AUTO] MX-7103 at 12.6% deviation."
    )


class TestParsePayload:
    """Tests for action_loop._parse_payload."""

    def test_round_trips_a_built_payload(self):
        parsed = action_loop._parse_payload(_payload())
        assert parsed["title"] == "Manufacturing Alert: MX-7103"

    def test_accepts_a_json_string(self):
        parsed = action_loop._parse_payload(json.dumps(_payload()))
        assert parsed["title"] == "Manufacturing Alert: MX-7103"

    def test_extracts_the_message_paragraph(self):
        assert "12.6% deviation" in action_loop._parse_payload(_payload())["message"]

    def test_extracts_every_labelled_field(self):
        labels = [label for label, _ in action_loop._parse_payload(_payload())["fields"]]
        assert labels == ["Severity", "Source", "Timestamp", "Machine"]

    def test_severity_field_carries_the_value(self):
        fields = dict(action_loop._parse_payload(_payload())["fields"])
        assert fields["Severity"] == "WARNING"
        assert fields["Machine"] == "MX-7103"

    @pytest.mark.parametrize(
        "bad",
        ['{"garbage": 1}', "{}", "not json at all", '{"cardsV2": []}', "[]"],
    )
    def test_malformed_payloads_raise_the_domain_error(self, bad):
        with pytest.raises(action_loop.WebhookPayloadError):
            action_loop._parse_payload(bad)

    def test_none_raises_the_domain_error(self):
        with pytest.raises(action_loop.WebhookPayloadError):
            action_loop._parse_payload(None)

    def test_error_is_a_valueerror_subclass(self):
        assert issubclass(action_loop.WebhookPayloadError, ValueError)
