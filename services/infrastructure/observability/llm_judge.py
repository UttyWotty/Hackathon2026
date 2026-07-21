"""
LLM-as-judge evaluators for automated quality scoring.

Uses the raw (untraced) MLX LLM instance with use_case="fast" to avoid
recursive tracing. Each judge returns a (score, reason) tuple where
score is 0.0-1.0 and reason is a short explanation.
"""

from __future__ import annotations

import json
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_OUTPUT_LENGTH = 2000
MAX_JUDGE_TOKENS = 256
JUDGE_TEMPERATURE = 0.1

DOMAIN_TERMS = [
    "MTTR",
    "MTBF",
    "OEE",
    "cycle time",
    "shot count",
    "run rate",
    "downtime",
    "uptime",
    "availability",
    "performance",
    "quality",
    "scrap rate",
    "yield",
    "changeover",
    "tooling",
    "EOL",
    "cavity",
    "tonnage",
    "injection",
    "molding",
    "die cast",
    "press",
    "stamping",
    "CNC",
    "machining",
    "PPM",
]

RELEVANCE_PROMPT = """Rate how relevant and helpful this response is on a scale of 0.0 to 1.0.
Consider: Does it directly address a question? Is it coherent? Does it provide useful information?

Response to evaluate:
---
{output}
---

Return ONLY a JSON object: {{"score": 0.0-1.0, "reason": "brief explanation"}}"""

HALLUCINATION_PROMPT = """Rate the hallucination risk of this response on a scale of 0.0 to 1.0.
0.0 = no hallucination risk (factual, hedged, or clearly stated)
1.0 = high hallucination risk (unsupported claims, invented data, false specifics)

Look for: invented statistics, fake references, unsupported causal claims, fabricated data points.

Response to evaluate:
---
{output}
---

Return ONLY a JSON object: {{"score": 0.0-1.0, "reason": "brief explanation"}}"""

DOMAIN_ACCURACY_PROMPT = """Rate the manufacturing domain accuracy of this response on a scale of 0.0 to 1.0.
Consider: Are manufacturing terms (MTTR, MTBF, OEE, cycle time, etc.) used correctly?
Are formulas and calculations accurate? Are industry concepts applied properly?

If the response is not about manufacturing, return 1.0 (not applicable).

Response to evaluate:
---
{output}
---

Return ONLY a JSON object: {{"score": 0.0-1.0, "reason": "brief explanation"}}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def judge_relevance(output: str) -> Tuple[float, str]:
    """Judge how relevant and helpful a response is.

    Args:
        output: LLM response text to evaluate.

    Returns:
        Tuple of (score 0.0-1.0, reason string).
    """
    truncated = output[:MAX_OUTPUT_LENGTH]
    prompt = RELEVANCE_PROMPT.format(output=truncated)
    return _run_judge(
        prompt, fallback_score=0.5, fallback_reason="Could not evaluate relevance"
    )


def judge_hallucination_risk(output: str) -> Tuple[float, str]:
    """Judge the hallucination risk of a response.

    Args:
        output: LLM response text to evaluate.

    Returns:
        Tuple of (score 0.0-1.0 where higher = more risk, reason string).
    """
    truncated = output[:MAX_OUTPUT_LENGTH]
    prompt = HALLUCINATION_PROMPT.format(output=truncated)
    return _run_judge(
        prompt,
        fallback_score=0.5,
        fallback_reason="Could not evaluate hallucination risk",
    )


def judge_domain_accuracy(output: str) -> Tuple[float, str]:
    """Judge manufacturing domain accuracy of a response.

    If the response does not contain any manufacturing terminology,
    returns (1.0, "No domain terms found, not applicable") without
    calling the LLM.

    Args:
        output: LLM response text to evaluate.

    Returns:
        Tuple of (score 0.0-1.0, reason string).
    """
    output_upper = output.upper()
    has_domain_content = any(term.upper() in output_upper for term in DOMAIN_TERMS)

    if not has_domain_content:
        return 1.0, "No domain terms found, not applicable"

    truncated = output[:MAX_OUTPUT_LENGTH]
    prompt = DOMAIN_ACCURACY_PROMPT.format(output=truncated)
    return _run_judge(
        prompt,
        fallback_score=0.5,
        fallback_reason="Could not evaluate domain accuracy",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_raw_llm() -> object:
    """Get the raw (untraced) MLX LLM instance.

    Returns:
        The _raw_mlx_llm instance from the mlx_llm module.

    Raises:
        ImportError: If the MLX LLM module is not available.
    """
    from services.infrastructure.ml.mlx_llm import _raw_mlx_llm

    return _raw_mlx_llm


def _run_judge(
    prompt: str,
    fallback_score: float,
    fallback_reason: str,
) -> Tuple[float, str]:
    """Execute a judge prompt and parse the structured JSON response.

    Args:
        prompt: The evaluation prompt to send to the LLM.
        fallback_score: Score to return if parsing fails.
        fallback_reason: Reason to return if parsing fails.

    Returns:
        Tuple of (score, reason).
    """
    try:
        llm = _get_raw_llm()
        response = llm.chat(  # type: ignore[union-attr]
            messages=[{"role": "user", "content": prompt}],
            use_case="fast",
            max_tokens=MAX_JUDGE_TOKENS,
            temperature=JUDGE_TEMPERATURE,
        )
        return _parse_judge_response(response.content, fallback_score, fallback_reason)

    except ImportError:
        logger.debug("MLX LLM not available for judge evaluation")
        return fallback_score, fallback_reason
    except Exception:
        logger.debug("Judge evaluation failed", exc_info=True)
        return fallback_score, fallback_reason


def _parse_judge_response(
    raw: str,
    fallback_score: float,
    fallback_reason: str,
) -> Tuple[float, str]:
    """Parse a JSON judge response, with fallback for malformed output.

    Handles cases where the LLM wraps JSON in markdown code blocks
    or includes extra text around the JSON object.

    Args:
        raw: Raw LLM response text.
        fallback_score: Default score if parsing fails.
        fallback_reason: Default reason if parsing fails.

    Returns:
        Tuple of (score, reason).
    """
    text = raw.strip()

    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    # Try direct JSON parse
    try:
        data = json.loads(text)
        return _validate_judge_data(data, fallback_score, fallback_reason)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON object from surrounding text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return _validate_judge_data(data, fallback_score, fallback_reason)
        except json.JSONDecodeError:
            pass

    logger.debug("Could not parse judge response: %s", text[:200])
    return fallback_score, fallback_reason


def _validate_judge_data(
    data: dict,
    fallback_score: float,
    fallback_reason: str,
) -> Tuple[float, str]:
    """Validate and clamp the parsed judge data.

    Args:
        data: Parsed JSON dictionary.
        fallback_score: Default score if validation fails.
        fallback_reason: Default reason if validation fails.

    Returns:
        Tuple of (clamped score, reason).
    """
    if not isinstance(data, dict):
        return fallback_score, fallback_reason

    score = data.get("score")
    reason = data.get("reason", fallback_reason)

    if score is None or not isinstance(score, (int, float)):
        return fallback_score, str(reason)

    clamped = max(0.0, min(1.0, float(score)))
    return clamped, str(reason)
