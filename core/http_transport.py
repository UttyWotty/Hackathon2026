"""
Shared HTTP transport for the LLM clients.

Defines the Transport callable contract and a single requests-backed
implementation, so the Cortex and MLX clients share one network surface and
both stay injectable for testing. This is the only module in the LLM path that
touches the network.
"""

from typing import Any, Callable, Dict

from .cortex_errors import CortexRequestError

# Truncation applied to an error body before it reaches a log line.
ERROR_BODY_LIMIT = 500

# A transport takes (url, headers, payload, timeout) and returns parsed JSON.
Transport = Callable[[str, Dict[str, str], Dict[str, Any], int], Dict[str, Any]]


def post_json(
    url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int
) -> Dict[str, Any]:
    """
    POST a JSON body and return the parsed JSON response.

    Args:
        url: Fully qualified endpoint.
        headers: Request headers.
        payload: JSON request body.
        timeout: Socket timeout in seconds.

    Returns:
        The parsed JSON response.

    Raises:
        CortexRequestError: On any transport failure or non-2xx status.
    """
    import requests

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout as exc:
        # Distinguished from a refused connection: the endpoint accepted the
        # request and was still working when the clock ran out. Retrying will
        # not help; either the prompt is too large or the timeout is too short.
        raise CortexRequestError(
            f"LLM request to {url} timed out after {timeout}s. The endpoint is "
            f"reachable but did not finish generating."
        ) from exc
    except requests.ConnectionError as exc:
        raise CortexRequestError(
            f"Could not connect to {url}. Nothing appears to be listening."
        ) from exc
    except requests.RequestException as exc:
        raise CortexRequestError(f"LLM request to {url} failed: {exc}") from exc

    if response.status_code >= 400:
        raise CortexRequestError(
            f"LLM endpoint {url} returned HTTP {response.status_code}: "
            f"{response.text[:ERROR_BODY_LIMIT]}"
        )
    return response.json()
