"""Factory selecting the LLM backend the agent loop reasons with.

Reads LLM_BACKEND and returns a CortexClient for reasoning via Snowflake Cortex.
All callers use the same get_response contract.
"""

import logging
from typing import Any

from .cortex_errors import CortexConfigurationError

logger = logging.getLogger(__name__)

BACKEND_CORTEX = "cortex"


def get_llm_client(backend: str = BACKEND_CORTEX) -> Any:
    """
    Build the configured LLM client.

    Args:
        backend: Must be "cortex".

    Returns:
        A client exposing get_response(messages, tools, max_tokens,
        temperature, session_id).

    Raises:
        CortexConfigurationError: If the backend name is not recognised.
    """
    if backend == BACKEND_CORTEX:
        from .cortex_client import CortexClient

        return CortexClient()

    raise CortexConfigurationError(
        f"Unknown LLM_BACKEND {backend!r}. Expected 'cortex'."
    )
