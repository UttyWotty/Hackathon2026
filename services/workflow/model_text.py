"""
Helpers for handling raw model output before it is stored or scored.

Reasoning models wrap an internal scratchpad in <think> tags and put their
actual conclusion last, so naive head-truncation keeps the deliberation and
discards the answer. Pure string handling, shared by the recorder and scorer.
"""

import re

# Matches a complete scratchpad block.
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Matches an unterminated scratchpad, which happens when generation is cut off
# mid-thought. Everything from the opening tag onward is deliberation.
UNCLOSED_THINK_PATTERN = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)

TRUNCATION_MARKER = "... [truncated]"
TRUNCATION_PREFIX = "[truncated] ..."


def strip_reasoning(text: str) -> str:
    """
    Remove any <think> scratchpad, leaving the model's stated conclusion.

    Handles the unterminated case too: a run whose generation was cut off mid
    scratchpad has no conclusion, and returning the deliberation as if it were
    one would misrepresent the run.

    Args:
        text: Raw model output.

    Returns:
        The conclusion text, stripped of reasoning blocks. May be empty.
    """
    if not text:
        return ""
    cleaned = THINK_PATTERN.sub(" ", text)
    cleaned = UNCLOSED_THINK_PATTERN.sub(" ", cleaned)
    return cleaned.strip()


def truncate_keeping_tail(text: str, limit: int) -> str:
    """
    Shorten text while preserving its end.

    Used for model conclusions, where the operative content is last. The
    opposite of the head-truncation applied to structured tool results.

    Args:
        text: Text to shorten.
        limit: Maximum characters to keep, excluding the marker.

    Returns:
        The text, or its final `limit` characters marked as truncated.
    """
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return TRUNCATION_PREFIX + text[-limit:]
