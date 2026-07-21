"""
Transparent tracing proxy for MlxLLMService.

Wraps every LLM call (chat, chat_async, chat_stream, generate_sql, analyze,
quick_response) with Langfuse trace + generation spans. Delegates all other
attribute access to the inner service unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional

from services.infrastructure.ml.mlx_llm import ChatResponse, MlxLLMService
from services.infrastructure.observability.langfuse_client import (
    APP_RELEASE,
    APP_VERSION,
    get_langfuse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACE_NAME_CHAT = "mlx_chat"
TRACE_NAME_CHAT_STREAM = "mlx_chat_stream"
TRACE_NAME_GENERATE_SQL = "mlx_generate_sql"
TRACE_NAME_ANALYZE = "mlx_analyze"
TRACE_NAME_QUICK = "mlx_quick_response"

GENERATION_NAME_CHAT = "chat_completion"
GENERATION_NAME_STREAM = "stream_completion"
GENERATION_NAME_SQL = "sql_generation"
GENERATION_NAME_ANALYSIS = "analysis"
GENERATION_NAME_QUICK = "quick_response"


class TracedMlxLLMService:
    """Proxy that wraps MlxLLMService to emit Langfuse traces.

    If Langfuse is unavailable (disabled, keys missing, package absent),
    all methods delegate directly to the inner service with zero overhead.

    Attributes:
        _inner: The real MlxLLMService instance.
    """

    def __init__(self, inner: MlxLLMService) -> None:
        self._inner = inner

    # ------------------------------------------------------------------
    # Delegation for non-traced attributes
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the inner service."""
        return getattr(self._inner, name)

    # ------------------------------------------------------------------
    # Traced methods
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Any],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Chat completion with Langfuse tracing."""
        langfuse = get_langfuse()
        if langfuse is None:
            return self._inner.chat(
                messages,
                model,
                use_case,
                temperature,
                max_tokens,
                tools,
                system_prompt,
            )

        trace = langfuse.trace(
            name=TRACE_NAME_CHAT,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
            metadata={"use_case": use_case or "general"},
        )
        generation = trace.generation(
            name=GENERATION_NAME_CHAT,
            model=model or use_case or "default",
            input=_extract_last_user_message(messages),
            metadata={"temperature": temperature, "max_tokens": max_tokens},
        )

        start = time.perf_counter()
        try:
            response = self._inner.chat(
                messages,
                model,
                use_case,
                temperature,
                max_tokens,
                tools,
                system_prompt,
            )
            duration_ms = (time.perf_counter() - start) * 1000

            generation.end(
                output=response.content,
                model=getattr(response.model, "value", str(response.model)),
                usage={
                    "input": response.prompt_eval_count,
                    "output": response.eval_count,
                },
                metadata={
                    "finish_reason": response.finish_reason,
                    "duration_ms": round(duration_ms, 1),
                },
            )

            _schedule_scoring(trace, response, duration_ms)
            return response

        except Exception as exc:
            generation.end(
                output=str(exc),
                level="ERROR",
                status_message=str(exc),
            )
            raise

    async def chat_async(
        self,
        messages: List[Any],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Async chat completion with Langfuse tracing."""
        langfuse = get_langfuse()
        if langfuse is None:
            return await self._inner.chat_async(
                messages,
                model,
                use_case,
                temperature,
                max_tokens,
                tools,
                system_prompt,
            )

        trace = langfuse.trace(
            name=TRACE_NAME_CHAT,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
            metadata={"use_case": use_case or "general", "async": True},
        )
        generation = trace.generation(
            name=GENERATION_NAME_CHAT,
            model=model or use_case or "default",
            input=_extract_last_user_message(messages),
        )

        start = time.perf_counter()
        try:
            response = await self._inner.chat_async(
                messages,
                model,
                use_case,
                temperature,
                max_tokens,
                tools,
                system_prompt,
            )
            duration_ms = (time.perf_counter() - start) * 1000

            generation.end(
                output=response.content,
                model=getattr(response.model, "value", str(response.model)),
                usage={
                    "input": response.prompt_eval_count,
                    "output": response.eval_count,
                },
                metadata={
                    "finish_reason": response.finish_reason,
                    "duration_ms": round(duration_ms, 1),
                },
            )

            _schedule_scoring(trace, response, duration_ms)
            return response

        except Exception as exc:
            generation.end(output=str(exc), level="ERROR", status_message=str(exc))
            raise

    def chat_stream(
        self,
        messages: List[Any],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Iterator[str]:
        """Streaming chat with Langfuse tracing.

        Tokens are yielded in real time; trace is finalised when the
        stream completes.
        """
        langfuse = get_langfuse()
        if langfuse is None:
            yield from self._inner.chat_stream(
                messages,
                model,
                use_case,
                temperature,
                max_tokens,
                system_prompt,
            )
            return

        trace = langfuse.trace(
            name=TRACE_NAME_CHAT_STREAM,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
            metadata={"use_case": use_case or "general", "streaming": True},
        )
        generation = trace.generation(
            name=GENERATION_NAME_STREAM,
            model=model or use_case or "default",
            input=_extract_last_user_message(messages),
        )

        collected: list[str] = []
        start = time.perf_counter()
        try:
            for token in self._inner.chat_stream(
                messages,
                model,
                use_case,
                temperature,
                max_tokens,
                system_prompt,
            ):
                collected.append(token)
                yield token

            duration_ms = (time.perf_counter() - start) * 1000
            full_output = "".join(collected)
            generation.end(
                output=full_output,
                metadata={"duration_ms": round(duration_ms, 1)},
            )
        except Exception as exc:
            generation.end(output=str(exc), level="ERROR", status_message=str(exc))
            raise

    def generate_sql(
        self,
        prompt: str,
        schema_context: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """SQL generation with Langfuse tracing."""
        langfuse = get_langfuse()
        if langfuse is None:
            return self._inner.generate_sql(prompt, schema_context, max_tokens)

        trace = langfuse.trace(
            name=TRACE_NAME_GENERATE_SQL,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
            metadata={"has_schema": schema_context is not None},
        )
        generation = trace.generation(
            name=GENERATION_NAME_SQL,
            model="coder",
            input=prompt,
        )

        start = time.perf_counter()
        try:
            result = self._inner.generate_sql(prompt, schema_context, max_tokens)
            duration_ms = (time.perf_counter() - start) * 1000
            generation.end(
                output=result,
                metadata={"duration_ms": round(duration_ms, 1)},
            )
            return result
        except Exception as exc:
            generation.end(output=str(exc), level="ERROR", status_message=str(exc))
            raise

    def analyze(
        self,
        data: str,
        question: str,
        max_tokens: int = 4096,
    ) -> str:
        """Deep analysis with Langfuse tracing."""
        langfuse = get_langfuse()
        if langfuse is None:
            return self._inner.analyze(data, question, max_tokens)

        trace = langfuse.trace(
            name=TRACE_NAME_ANALYZE,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
        )
        generation = trace.generation(
            name=GENERATION_NAME_ANALYSIS,
            model="reasoning",
            input=question,
            metadata={"data_length": len(data)},
        )

        start = time.perf_counter()
        try:
            result = self._inner.analyze(data, question, max_tokens)
            duration_ms = (time.perf_counter() - start) * 1000
            generation.end(
                output=result,
                metadata={"duration_ms": round(duration_ms, 1)},
            )
            return result
        except Exception as exc:
            generation.end(output=str(exc), level="ERROR", status_message=str(exc))
            raise

    def quick_response(
        self,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """Quick response with Langfuse tracing."""
        langfuse = get_langfuse()
        if langfuse is None:
            return self._inner.quick_response(prompt, max_tokens)

        trace = langfuse.trace(
            name=TRACE_NAME_QUICK,
            id=str(uuid.uuid4()),
            version=APP_VERSION,
            release=APP_RELEASE,
        )
        generation = trace.generation(
            name=GENERATION_NAME_QUICK,
            model="fast",
            input=prompt,
        )

        start = time.perf_counter()
        try:
            result = self._inner.quick_response(prompt, max_tokens)
            duration_ms = (time.perf_counter() - start) * 1000
            generation.end(
                output=result,
                metadata={"duration_ms": round(duration_ms, 1)},
            )
            return result
        except Exception as exc:
            generation.end(output=str(exc), level="ERROR", status_message=str(exc))
            raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_last_user_message(messages: List[Any]) -> str:
    """Pull the last user message content for trace input."""
    for msg in reversed(messages):
        if isinstance(msg, dict):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        elif hasattr(msg, "role") and msg.role == "user":
            return str(msg.content)
    return ""


def _schedule_scoring(trace: Any, response: ChatResponse, duration_ms: float) -> None:
    """Fire-and-forget async scoring for a completed trace."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    from services.infrastructure.observability.scoring import score_trace_async

    loop.create_task(
        score_trace_async(
            trace=trace,
            output=response.content,
            duration_ms=duration_ms,
            prompt_tokens=response.prompt_eval_count,
            completion_tokens=response.eval_count,
        )
    )
