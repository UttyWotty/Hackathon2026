"""
Shared HTTP transport for the LLM clients.

Defines the Transport callable contract and a single requests-backed
implementation with retry/backoff, so the Cortex client has one network surface
that stays injectable for testing. This is the only module in the LLM path that
touches the network.
"""

import logging
from typing import Any, Callable, Dict

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cortex_errors import CortexRequestError

logger = logging.getLogger(__name__)

# Truncation applied to an error body before it reaches a log line.
ERROR_BODY_LIMIT = 500

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
BACKOFF_MIN_SECONDS = 1
BACKOFF_MAX_SECONDS = 8

# A transport takes (url, headers, payload, timeout) and returns parsed JSON.
Transport = Callable[[str, Dict[str, str], Dict[str, Any], int], Dict[str, Any]]


class _RetryableRequestError(CortexRequestError):
    """Subclass indicating the request can be retried (429/5xx)."""


@retry(
    retry=retry_if_exception_type(_RetryableRequestError),
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(min=BACKOFF_MIN_SECONDS, max=BACKOFF_MAX_SECONDS),
    reraise=True,
    before_sleep=lambda rs: logger.warning(
        "LLM request retry attempt %d after %s", rs.attempt_number, rs.outcome.exception()
    ),
)
def post_json(
    url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int
) -> Dict[str, Any]:
    """
    POST a JSON body and return the parsed JSON response.

    Retries up to 3 times with exponential backoff on 429/5xx responses.

    Args:
        url: Fully qualified endpoint.
        headers: Request headers.
        payload: JSON request body.
        timeout: Socket timeout in seconds.

    Returns:
        The parsed JSON response.

    Raises:
        CortexRequestError: On any transport failure or non-2xx status after retries.
    """
    import requests

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout as exc:
        raise CortexRequestError(
            f"LLM request to {url} timed out after {timeout}s. The endpoint is "
            f"reachable but did not finish generating."
        ) from exc
    except requests.ConnectionError as exc:
        raise _RetryableRequestError(
            f"Could not connect to {url}. Nothing appears to be listening."
        ) from exc
    except requests.RequestException as exc:
        raise CortexRequestError(f"LLM request to {url} failed: {exc}") from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise _RetryableRequestError(
            f"LLM endpoint {url} returned HTTP {response.status_code}: "
            f"{response.text[:ERROR_BODY_LIMIT]}"
        )

    if response.status_code >= 400:
        raise CortexRequestError(
            f"LLM endpoint {url} returned HTTP {response.status_code}: "
            f"{response.text[:ERROR_BODY_LIMIT]}"
        )
    return response.json()
