"""Forwards alerts written by the dashboard to an external webhook.

Streamlit in Snowflake cannot make outbound HTTP calls without an External
Access Integration, so the dashboard records each alert into AUDIT_LOG with its
full Cards v2 payload instead of posting it. This script watches that table and
delivers new payloads, which is what makes the alert appear in a browser tab
moments after the button is pressed.

Usage:
    python scripts/alert_bridge.py
    python scripts/alert_bridge.py --backfill 3   # also send the last 3 alerts
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT.parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("services.infrastructure.snowflake.session_pool").setLevel(
    logging.CRITICAL
)
logger = logging.getLogger("alert_bridge")

POLL_SECONDS = float(os.getenv("ALERT_BRIDGE_POLL_SECONDS", "2"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("ALERT_BRIDGE_TIMEOUT", "10"))
WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL", "").strip()

AUDIT_TABLE = "DEMO.PUBLIC.AUDIT_LOG"

LATEST_QUERY = f"""
SELECT TIMESTAMP, MACHINE_ID, SEVERITY, DESCRIPTION,
       WEBHOOK_PAYLOAD::VARCHAR AS PAYLOAD
FROM {AUDIT_TABLE}
WHERE ACTION_TYPE = 'ALERT' AND WEBHOOK_PAYLOAD IS NOT NULL
ORDER BY TIMESTAMP DESC
LIMIT {{limit}}
"""


class AlertBridgeError(RuntimeError):
    """Raised when the bridge cannot start or deliver."""


def _query(sql: str) -> List[dict]:
    """Run a read-only query and return records."""
    from services.config.features.insights.tools.common import query_records

    return query_records(sql)


def post_payload(url: str, payload: str) -> int:
    """POST one JSON payload and return the HTTP status code.

    Args:
        url: Destination webhook URL.
        payload: JSON document as text.

    Returns:
        The HTTP status code.

    Raises:
        AlertBridgeError: If the request could not be completed.
    """
    request = urllib.request.Request(
        url,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError as exc:
        raise AlertBridgeError(f"Could not reach {url}: {exc.reason}") from exc


def describe(row: dict) -> str:
    """Build a one-line console description of an alert row."""
    title = "alert"
    try:
        payload = json.loads(row["PAYLOAD"])
        title = payload["cardsV2"][0]["card"]["header"]["title"]
    except (KeyError, TypeError, IndexError, ValueError):
        pass
    return f"{row.get('SEVERITY', '?'):<8} {row.get('MACHINE_ID', '?'):<10} {title}"


def run(url: str, backfill: int) -> None:
    """Watch AUDIT_LOG and forward each new alert payload.

    Args:
        url: Destination webhook URL.
        backfill: How many existing alerts to send on startup.
    """
    rows = _query(LATEST_QUERY.format(limit=max(backfill, 1)))
    watermark: Optional[str] = rows[0]["TIMESTAMP"] if rows else None

    if backfill and rows:
        for row in reversed(rows[:backfill]):
            status = post_payload(url, row["PAYLOAD"])
            logger.info("  backfill -> HTTP %s  %s", status, describe(row))

    logger.info("")
    logger.info("Watching %s for new alerts. Press the Alert button in the", AUDIT_TABLE)
    logger.info("dashboard and it will appear in your webhook tab. Ctrl+C to stop.")
    logger.info("")

    while True:
        try:
            rows = _query(LATEST_QUERY.format(limit=5))
        except Exception as exc:  # noqa: BLE001 - keep the demo bridge alive
            logger.warning("  query failed, retrying: %s", exc)
            time.sleep(POLL_SECONDS)
            continue

        fresh = [r for r in rows if watermark is None or r["TIMESTAMP"] > watermark]
        for row in reversed(fresh):
            try:
                status = post_payload(url, row["PAYLOAD"])
                logger.info("  delivered -> HTTP %s  %s", status, describe(row))
            except AlertBridgeError as exc:
                logger.warning("  delivery failed: %s", exc)
        if fresh:
            watermark = fresh[0]["TIMESTAMP"]

        time.sleep(POLL_SECONDS)


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="Send this many existing alerts on startup (default: 0).",
    )
    parser.add_argument(
        "--url",
        default=WEBHOOK_URL,
        help="Webhook URL. Defaults to GOOGLE_CHAT_WEBHOOK_URL.",
    )
    args = parser.parse_args()

    if not args.url:
        logger.error(
            "No webhook URL. Set GOOGLE_CHAT_WEBHOOK_URL in .env or pass --url."
        )
        return 1

    logger.info("=" * 68)
    logger.info("alert bridge -> %s", args.url)
    logger.info("=" * 68)

    try:
        run(args.url, args.backfill)
    except KeyboardInterrupt:
        logger.info("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
