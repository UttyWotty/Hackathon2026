"""
Transparent tracing proxy for BedrockClient.

Wraps get_response() with Langfuse trace + generation spans to capture
model, messages, tools, token usage, stop reason, and duration.
Delegates all other attribute access unchanged.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

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

TRACE_NAME_BEDROCK = "bedrock_converse"
GENERATION_NAME_BEDROCK = "bedrock_generation"


class TracedBedrockClient:
    """Proxy that wraps BedrockClient to emit Langfuse traces.

    If Langfuse is unavailable, all calls pass through with zero overhead.

    Attributes:
        _inner: The real BedrockClient instance.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the inner client."""
        return getattr(self._inner, name)

    def get_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        session_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """Call Bedrock converse with Langfuse tracing."""
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
            name=TRACE_NAME_BEDROCK,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
            session_id=session_id,
            metadata={
                "model_id": self._inner.model_id,
                "has_tools": tools is not None,
                "tool_count": len(tools) if tools else 0,
            },
        )
        generation = trace.generation(
            name=GENERATION_NAME_BEDROCK,
            model=self._inner.model_id,
            input=_extract_bedrock_input(messages),
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
                stop_reason = response.get("stopReason", "unknown")
                output_text = _extract_bedrock_output(response)

                generation.end(
                    output=output_text,
                    usage={
                        "input": usage.get("inputTokens", 0),
                        "output": usage.get("outputTokens", 0),
                    },
                    metadata={
                        "stop_reason": stop_reason,
                        "duration_ms": round(duration_ms, 1),
                    },
                )
            else:
                generation.end(
                    output="No response from Bedrock",
                    level="WARNING",
                    status_message="Bedrock returned None",
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


def get_traced_bedrock_client() -> Any:
    """Return a traced or raw BedrockClient based on configuration.

    Returns:
        TracedBedrockClient if Langfuse is enabled, otherwise raw BedrockClient.
    """
    from core.llm_client import BedrockClient

    raw_client = BedrockClient()

    if LANGFUSE_ENABLED:
        return TracedBedrockClient(raw_client)

    return raw_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_bedrock_input(messages: List[Dict[str, Any]]) -> str:
    """Extract the last user message text from Bedrock-formatted messages."""
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


def _extract_bedrock_output(response: Dict[str, Any]) -> str:
    """Extract text content from a Bedrock converse response."""
    try:
        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])
        parts = []
        for block in content_blocks:
            if "text" in block:
                parts.append(block["text"])
        return "\n".join(parts) if parts else ""
    except Exception:
        return ""
