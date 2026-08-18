"""
Factory selecting the LLM backend the agent loop reasons with.

Reads LLM_BACKEND and returns either a CortexClient (the default and the only
submission path) or an MLXClient for local development against mlx_lm.server.
Both expose the same get_response contract, so callers never branch on backend.
"""

import logging
import os
from typing import Any

from .cortex_errors import CortexConfigurationError

logger = logging.getLogger(__name__)

BACKEND_CORTEX = "cortex"
BACKEND_MLX = "mlx"
SUPPORTED_BACKENDS = (BACKEND_CORTEX, BACKEND_MLX)

# Cortex is the default deliberately: the contest rewards Cortex-native
# reasoning, and tool dispatch across the full registry is materially less
# reliable on a quantized local model. MLX is opt-in, for iteration only.
LLM_BACKEND = os.getenv("LLM_BACKEND", BACKEND_CORTEX).strip().lower()


def get_llm_client(backend: str = LLM_BACKEND) -> Any:
    """
    Build the configured LLM client.

    Args:
        backend: Either "cortex" or "mlx". Defaults to the LLM_BACKEND env var,
            which itself defaults to "cortex".

    Returns:
        A client exposing get_response(messages, tools, max_tokens,
        temperature, session_id).

    Raises:
        CortexConfigurationError: If the backend name is not recognised.
    """
    if backend == BACKEND_CORTEX:
        from .cortex_client import CortexClient

        return CortexClient()

    if backend == BACKEND_MLX:
        from .mlx_client import MLXClient

        logger.warning(
            "LLM_BACKEND=mlx: reasoning on a local model. This is a development "
            "backend only and must not be used for the demo or submission."
        )
        return MLXClient()

    raise CortexConfigurationError(
        f"Unknown LLM_BACKEND {backend!r}. Expected one of {SUPPORTED_BACKENDS}."
    )
