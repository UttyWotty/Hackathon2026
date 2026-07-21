"""
Automated scoring pipeline for Langfuse traces.

Provides inline scorers (latency, cost, SQL correctness) that run synchronously,
plus an async dispatcher that enqueues LLM-as-judge evaluations for relevance,
hallucination risk, and domain accuracy.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional, Tuple

from services.infrastructure.observability.langfuse_client import get_langfuse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class ScoreType(str, Enum):
    """Identifiers for each automated score."""

    RELEVANCE = "relevance"
    LATENCY = "latency"
    TOKEN_COST = "token_cost"
    HALLUCINATION = "hallucination"
    SQL_CORRECTNESS = "sql_correctness"
    DOMAIN_ACCURACY = "domain_accuracy"


# Latency thresholds (seconds)
LATENCY_EXCELLENT_SECONDS = 2.0
LATENCY_GOOD_SECONDS = 5.0
LATENCY_ACCEPTABLE_SECONDS = 10.0
LATENCY_POOR_SECONDS = 30.0

# Token cost budget per call
TOKEN_BUDGET_PER_CALL = 8000
TOKEN_BUDGET_EXPENSIVE = 16000


# ---------------------------------------------------------------------------
# Inline scorers
# ---------------------------------------------------------------------------


def score_latency(duration_ms: float) -> Tuple[float, str]:
    """Score latency on a 0-1 scale based on response duration.

    Args:
        duration_ms: Response duration in milliseconds.

    Returns:
        Tuple of (score, comment) where score is 0.0 (terrible) to 1.0 (excellent).
    """
    duration_s = duration_ms / 1000.0

    if duration_s <= LATENCY_EXCELLENT_SECONDS:
        score = 1.0
        comment = "Excellent latency (under 2s)"
    elif duration_s <= LATENCY_GOOD_SECONDS:
        score = 0.8
        comment = "Good latency (2-5s)"
    elif duration_s <= LATENCY_ACCEPTABLE_SECONDS:
        score = 0.6
        comment = "Acceptable latency (5-10s)"
    elif duration_s <= LATENCY_POOR_SECONDS:
        score = 0.3
        comment = "Slow response (10-30s)"
    else:
        score = 0.1
        comment = "Very slow response (over 30s)"

    return score, comment


def score_token_cost(
    prompt_tokens: int,
    completion_tokens: int,
) -> Tuple[float, str]:
    """Score token cost on a 0-1 scale based on total tokens used.

    Args:
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.

    Returns:
        Tuple of (score, comment).
    """
    total = prompt_tokens + completion_tokens

    if total <= TOKEN_BUDGET_PER_CALL:
        score = 1.0
        comment = "Within budget (%d tokens)" % total
    elif total <= TOKEN_BUDGET_EXPENSIVE:
        ratio = 1.0 - (
            (total - TOKEN_BUDGET_PER_CALL)
            / (TOKEN_BUDGET_EXPENSIVE - TOKEN_BUDGET_PER_CALL)
        )
        score = max(0.3, ratio)
        comment = "Above budget (%d tokens)" % total
    else:
        score = 0.1
        comment = "Expensive call (%d tokens)" % total

    return score, comment


def score_sql_correctness(output: str) -> Tuple[float, str]:
    """Score SQL correctness by running the output through sql_validation.

    Only applies if the output appears to contain SQL. Returns 1.0 with
    a skip comment for non-SQL outputs.

    Args:
        output: LLM response text.

    Returns:
        Tuple of (score, comment).
    """
    sql_indicators = ("SELECT ", "WITH ", "FROM ", "WHERE ")
    output_upper = output.upper().strip()

    has_sql = any(indicator in output_upper for indicator in sql_indicators)
    if not has_sql:
        return 1.0, "Non-SQL output, skipped"

    try:
        from utils.sql_validation import validate_sql_query

        sql_block = _extract_sql_block(output)
        if not sql_block:
            return 0.5, "Could not extract clean SQL block"

        _sanitized, is_read_only = validate_sql_query(sql_block)
        if is_read_only:
            return 1.0, "Valid read-only SQL"
        return 0.3, "SQL is not read-only"

    except Exception as exc:
        return 0.0, "SQL validation failed: %s" % str(exc)


# ---------------------------------------------------------------------------
# Async scoring entry point
# ---------------------------------------------------------------------------


async def score_trace_async(
    trace: Any,
    output: str,
    duration_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Run inline scores and dispatch LLM judge tasks for a trace.

    This is called as a fire-and-forget coroutine after each LLM call.
    Failures are logged but never propagated.

    Args:
        trace: Langfuse trace object to attach scores to.
        output: LLM response text.
        duration_ms: Call duration in milliseconds.
        prompt_tokens: Input token count.
        completion_tokens: Output token count.
    """
    langfuse = get_langfuse()
    if langfuse is None:
        return

    # Inline scores (cheap, run immediately)
    _apply_inline_scores(
        trace,
        output,
        duration_ms,
        prompt_tokens,
        completion_tokens,
    )

    # LLM judge scores (async, deferred)
    await _dispatch_llm_judges(trace, output)


def _apply_inline_scores(
    trace: Any,
    output: str,
    duration_ms: float,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Compute and attach inline scores to a trace."""
    scores = [
        (ScoreType.LATENCY, *score_latency(duration_ms)),
        (ScoreType.TOKEN_COST, *score_token_cost(prompt_tokens, completion_tokens)),
        (ScoreType.SQL_CORRECTNESS, *score_sql_correctness(output)),
    ]

    for score_name, score_value, comment in scores:
        try:
            trace.score(
                name=score_name.value,
                value=score_value,
                comment=comment,
            )
        except Exception:
            logger.debug("Failed to attach score %s", score_name.value, exc_info=True)


async def _dispatch_llm_judges(trace: Any, output: str) -> None:
    """Run LLM-as-judge evaluations and attach scores.

    Uses the raw MLX instance with use_case="fast" to avoid recursive tracing.
    Failures are logged and swallowed.
    """
    if not output or len(output) < 10:
        return

    try:
        from services.infrastructure.observability.llm_judge import (
            judge_domain_accuracy,
            judge_hallucination_risk,
            judge_relevance,
        )

        judges = [
            (ScoreType.RELEVANCE, judge_relevance),
            (ScoreType.HALLUCINATION, judge_hallucination_risk),
            (ScoreType.DOMAIN_ACCURACY, judge_domain_accuracy),
        ]

        for score_type, judge_fn in judges:
            try:
                score_value, reason = judge_fn(output)
                trace.score(
                    name=score_type.value,
                    value=score_value,
                    comment=reason,
                )
            except Exception:
                logger.debug(
                    "LLM judge %s failed",
                    score_type.value,
                    exc_info=True,
                )

    except ImportError:
        logger.debug("LLM judge module not available")
    except Exception:
        logger.debug("LLM judge dispatch failed", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_sql_block(text: str) -> Optional[str]:
    """Extract a SQL query from markdown code blocks or raw text.

    Args:
        text: Text potentially containing SQL.

    Returns:
        Extracted SQL string, or None if no SQL found.
    """
    import re

    # Try markdown code block first
    match = re.search(r"```(?:sql)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Try to find a raw SELECT/WITH statement
    match = re.search(
        r"((?:SELECT|WITH)\s+.+?)(?:\n\n|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    return None
