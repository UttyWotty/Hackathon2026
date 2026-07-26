"""
Transparent tracing proxy for the active LLM client.

Wraps get_response() with Langfuse trace + generation spans to capture
model, messages, tools, token usage, stop reason, and duration.
Backend-agnostic: it proxies whatever client llm_backend selects, and
delegates all other attribute access unchanged.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.cortex_wire import extract_text_from_response, get_stop_reason
from services.infrastructure.observability.langfuse_client import (
    APP_RELEASE,
    APP_VERSION,
    LANGFUSE_ENABLED,
    get_langfuse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACE_NAME_LLM = "llm_call"
UNKNOWN_MODEL = "unknown"
UNKNOWN_STOP_REASON = "unknown"
GENERATION_NAME_LLM = "llm_generation"


class TracedLLMClient:
    """Proxy that wraps an LLM client to emit Langfuse traces.

    If Langfuse is unavailable, all calls pass through with zero overhead.

    Attributes:
        _inner: The real client instance (Cortex or MLX).
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the inner client."""
        return getattr(self._inner, name)

    @property
    def _model_name(self) -> str:
        """Model identifier, tolerating either client's attribute name."""
        return getattr(self._inner, "model", None) or getattr(
            self._inner, "model_id", UNKNOWN_MODEL
        )

    def get_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        session_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """Call the inner client with Langfuse tracing."""
        langfuse = get_langfuse()
        if langfuse is None:
            return self._inner.get_response(
                messages,
                tools,
                max_tokens,
                temperature,
                session_id,
            )

        trace = langfuse.trace(
            name=TRACE_NAME_LLM,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
            session_id=session_id,
            metadata={
                "model_id": self._model_name,
                "has_tools": tools is not None,
                "tool_count": len(tools) if tools else 0,
            },
        )
        generation = trace.generation(
            name=GENERATION_NAME_LLM,
            model=self._model_name,
            input=_extract_last_user_text(messages),
            model_parameters={
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )

        start = time.perf_counter()
        try:
            response = self._inner.get_response(
                messages,
                tools,
                max_tokens,
                temperature,
                session_id,
            )
            duration_ms = (time.perf_counter() - start) * 1000

            if response is not None:
                usage = response.get("usage", {})
                stop_reason = get_stop_reason(response) or UNKNOWN_STOP_REASON
                output_text = extract_text_from_response(response)

                generation.end(
                    output=output_text,
                    usage={
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    },
                    metadata={
                        "stop_reason": stop_reason,
                        "duration_ms": round(duration_ms, 1),
                    },
                )
            else:
                generation.end(
                    output="No response from the LLM backend",
                    level="WARNING",
                    status_message="LLM client returned None",
                )

            return response

        except Exception as exc:
            generation.end(
                output=str(exc),
                level="ERROR",
                status_message=str(exc),
            )
            raise


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_traced_llm_client() -> Any:
    """Return a traced or raw LLM client for the configured backend.

    The backend itself is chosen by core.llm_backend from LLM_BACKEND; this
    function only decides whether to wrap it in tracing.

    Returns:
        TracedLLMClient if Langfuse is enabled, otherwise the raw client.
    """
    from core.llm_backend import get_llm_client

    raw_client = get_llm_client()

    if LANGFUSE_ENABLED:
        return TracedLLMClient(raw_client)

    return raw_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_last_user_text(messages: List[Dict[str, Any]]) -> str:
    """Extract the last user message text, tolerating string or block content."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        return block["text"]
            elif isinstance(content, str):
                return content
    return ""
