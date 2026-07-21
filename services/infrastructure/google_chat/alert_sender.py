"""
Public alert API for sending formatted failure notifications to Google Chat.
Provides in-memory throttling to prevent duplicate alerts and formats messages
as Google Chat Cards v2 with severity colour-coding, source, and timestamp.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.infrastructure.google_chat.client import (
    is_configured,
    send_webhook_message,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Throttle state  (module-level, reset on restart)
# ---------------------------------------------------------------------------
_last_sent: Dict[str, float] = {}  # alert_key → epoch timestamp


def _get_throttle_seconds() -> int:
    """Return the dedup window in seconds (default 300 = 5 min)."""
    try:
        return int(os.getenv("GOOGLE_CHAT_THROTTLE_SECONDS", "300"))
    except (ValueError, TypeError):
        return 300


def _is_throttled(alert_key: str) -> bool:
    """Return True if this alert_key was sent within the throttle window."""
    window = _get_throttle_seconds()
    last = _last_sent.get(alert_key)
    if last is None:
        return False
    return (time.monotonic() - last) < window


def _record_sent(alert_key: str) -> None:
    _last_sent[alert_key] = time.monotonic()


# ---------------------------------------------------------------------------
# Card formatting
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    "critical": "#D32F2F",
    "error": "#D32F2F",
    "warning": "#FFA000",
    "info": "#1976D2",
}


def _build_card_payload(
    title: str,
    message: str,
    severity: str,
    source: str,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a Google Chat Cards v2 payload."""
    _SEVERITY_COLORS.get(severity.lower(), "#757575")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    widgets: List[Dict[str, Any]] = [
        {
            "decoratedText": {
                "topLabel": "Severity",
                "text": severity.upper(),
            }
        },
        {
            "decoratedText": {
                "topLabel": "Source",
                "text": source,
            }
        },
        {
            "decoratedText": {
                "topLabel": "Timestamp",
                "text": timestamp,
            }
        },
        {
            "textParagraph": {
                "text": message[:2000],
            }
        },
    ]

    if extra_fields:
        for label, value in extra_fields.items():
            widgets.append(
                {
                    "decoratedText": {
                        "topLabel": str(label),
                        "text": str(value)[:500],
                    }
                }
            )

    return {
        "cardsV2": [
            {
                "cardId": "alertCard",
                "card": {
                    "header": {
                        "title": title[:200],
                        "subtitle": f"{severity.upper()} | {source}",
                        "imageUrl": "",
                        "imageType": "CIRCLE",
                    },
                    "sections": [
                        {
                            "header": "Alert Details",
                            "collapsible": False,
                            "widgets": widgets,
                        }
                    ],
                    "cardActions": [],
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_alert(
    title: str,
    message: str,
    severity: str = "error",
    source: str = "manufacturing-api",
    alert_key: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Send a formatted alert to Google Chat (fire-and-forget).

    This function never blocks and never raises.  It spawns the actual HTTP
    call via ``asyncio.create_task`` so callers are not delayed.

    Args:
        title: Short alert headline.
        message: Detailed alert body.
        severity: One of critical / error / warning / info.
        source: Subsystem that generated the alert.
        alert_key: Dedup key for throttling.  Defaults to ``title``.
        extra_fields: Optional key-value pairs added to the card.
    """
    if not is_configured():
        return

    key = alert_key or title
    if _is_throttled(key):
        logger.debug("Google Chat alert throttled (key=%s)", key)
        return

    _record_sent(key)

    payload = _build_card_payload(title, message, severity, source, extra_fields)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_safe_send(payload))
    except RuntimeError:
        # No running event loop — log and discard.
        logger.debug("No running event loop; Google Chat alert skipped")


async def _safe_send(payload: Dict[str, Any]) -> None:
    """Wrapper that swallows all exceptions so the task never crashes."""
    try:
        await send_webhook_message(payload)
    except Exception as exc:
        logger.warning("Google Chat alert task failed: %s", exc)
