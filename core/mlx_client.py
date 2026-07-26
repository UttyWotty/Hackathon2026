"""
Local MLX LLM client, a development stand-in for Cortex on Apple Silicon.

Talks to an mlx_lm.server OpenAI-compatible endpoint and returns responses in
the Anthropic shape, so the agent loop and the cortex_wire parsers are identical
across both backends. This is not a submission path; see llm_backend for why.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .cortex_errors import CortexRequestError
from .http_transport import Transport, post_json
from .mlx_wire import build_openai_payload, convert_response_to_anthropic
from .prompts import get_system_prompt
from .token_tracker import get_token_tracker

logger = logging.getLogger(__name__)

MLX_HOST = os.getenv("MLX_HOST", "http://127.0.0.1:8080")
MLX_LLM_MODEL = os.getenv("MLX_LLM_MODEL", "mlx-community/Qwen3-32B-4bit")
MLX_TIMEOUT_SECONDS = int(os.getenv("MLX_TIMEOUT_SECONDS", "300"))

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Defaults mirroring CortexClient so the two are drop-in interchangeable.
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
DEFAULT_SESSION_ID = "default"
DEFAULT_OPERATION = "chat_interface_mlx"


class MLXClient:
    """Client for a local mlx_lm.server, exposing the CortexClient interface."""

    # Recorded on every decision trail; see CortexClient.backend_name.
    backend_name = "mlx"

    def __init__(
        self,
        host: str = MLX_HOST,
        model: str = MLX_LLM_MODEL,
        timeout_seconds: int = MLX_TIMEOUT_SECONDS,
        transport: Optional[Transport] = None,
    ) -> None:
        """
        Initialise the local MLX client.

        Args:
            host: Base URL of mlx_lm.server. Defaults to the MLX_HOST env var.
            model: Model name as served. Defaults to MLX_LLM_MODEL.
            timeout_seconds: Per-request timeout. Local generation is slow, so
                this defaults far higher than the Cortex client's.
            transport: Injected transport callable. Defaults to requests.
        """
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport or post_json
        self.url = self.host + CHAT_COMPLETIONS_PATH
        logger.info("MLX client initialised: host=%s model=%s", self.host, self.model)

    def _track(self, response: Dict[str, Any], session_id: str) -> None:
        """Record token usage, never letting telemetry break the agent loop."""
        usage = response.get("usage", {})
        try:
            get_token_tracker().track_usage(
                model_id=self.model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                operation=DEFAULT_OPERATION,
                session_id=session_id,
            )
        except Exception:  # noqa: BLE001 - telemetry must not break chat
            logger.warning("Token tracking failed for session %s", session_id)

    def get_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a response from the local model, shaped like a Cortex response.

        Args:
            messages: Conversation turns in Anthropic format.
            tools: Tool definitions from get_tools_for_cortex, or None.
            max_tokens: Maximum tokens to generate. Defaults to 4096.
            temperature: Sampling temperature. Defaults to 0.7.
            session_id: Session identifier for token tracking.

        Returns:
            The response in Anthropic shape, or None if the request failed.
        """
        payload = build_openai_payload(
            messages=messages,
            system_prompt=get_system_prompt(),
            tools=tools,
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            raw = self.transport(self.url, {}, payload, self.timeout_seconds)
            response = convert_response_to_anthropic(raw)
        except CortexRequestError as exc:
            # The transport already distinguishes timeout from refusal, so log
            # its message rather than guessing at the cause.
            logger.error("MLX call failed: %s", exc)
            return None

        self._track(response, session_id)
        return response
