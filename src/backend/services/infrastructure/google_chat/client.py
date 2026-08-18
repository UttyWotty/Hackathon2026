"""
Low-level async HTTP client for posting messages to a Google Chat webhook.
Uses httpx for async HTTP and reads configuration from environment variables.
All public functions are safe to call unconditionally; they never raise exceptions.
"""

import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _get_webhook_url() -> str:
    """Return the configured Google Chat webhook URL, or empty string."""
    return os.getenv("GOOGLE_CHAT_WEBHOOK_URL", "").strip()


def _get_timeout() -> float:
    """Return the HTTP timeout in seconds (default 10)."""
    try:
        return float(os.getenv("GOOGLE_CHAT_TIMEOUT", "10"))
    except (ValueError, TypeError):
        return 10.0


def is_configured() -> bool:
    """Return True if a webhook URL is set in the environment."""
    return bool(_get_webhook_url())


# ---------------------------------------------------------------------------
# Core HTTP poster
# ---------------------------------------------------------------------------


async def send_webhook_message(payload: Dict[str, Any]) -> bool:
    """
    POST a JSON payload to the Google Chat webhook.

    Returns True on success, False on any error.  Never raises.
    """
    url = _get_webhook_url()
    if not url:
        logger.debug("Google Chat webhook URL not configured — skipping message")
        return False

    timeout = _get_timeout()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)

        if response.status_code == 200:
            logger.debug("Google Chat message sent successfully")
            return True

        logger.warning(
            "Google Chat webhook returned HTTP %s: %s",
            response.status_code,
            response.text[:200],
        )
        return False

    except httpx.TimeoutException:
        logger.warning("Google Chat webhook request timed out after %ss", timeout)
        return False
    except Exception as exc:
        logger.warning("Google Chat webhook request failed: %s", exc)
        return False
