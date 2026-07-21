"""Metric definitions and persistent insight notes tool adapters.

Serves canonical metric definitions (optionally with the full RunRate calculation
spec) and stores/retrieves analyst insights as tagged notes in the SQLite database.
Exposes the get_metric_definitions, save_insight, and get_insights MCP tools.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from analysis.insights.metric_definitions import get_definitions, list_metric_names
from models.database import get_session
from models.workflow import Note, normalize_tags

logger = logging.getLogger(__name__)

INSIGHT_TAG: str = "insight"
DEFAULT_INSIGHTS_LIMIT: int = 20
MAX_INSIGHTS_LIMIT: int = 100
NOTE_FETCH_MULTIPLIER: int = 5

PROJECT_ROOT: Path = Path(__file__).resolve().parents[5]
SPEC_FILE: Path = PROJECT_ROOT / "analysis" / "runrate" / "CALCULATION_SPEC.md"


def get_metric_definitions(
    metric: Optional[str] = None, include_spec: bool = False
) -> Dict[str, Any]:
    """Return canonical metric definitions used across all analyses.

    Args:
        metric: Optional single-metric filter (case-insensitive).
        include_spec: Also include the full RunRate calculation spec text.

    Returns:
        dict with definitions (and available_metrics when a filter misses).
    """
    try:
        definitions = get_definitions(metric)
        result: Dict[str, Any] = {"status": "success", "definitions": definitions}
        if metric and not definitions:
            result["available_metrics"] = list_metric_names()
        if include_spec:
            if SPEC_FILE.exists():
                result["calculation_spec"] = SPEC_FILE.read_text()
            else:
                result["calculation_spec_error"] = "Spec file not found: %s" % SPEC_FILE
        return result
    except Exception as e:
        logger.error("get_metric_definitions failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def save_insight(
    title: str, content: str, tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Persist an analyst insight as a tagged note.

    Args:
        title: Short insight title.
        content: The finding, with enough context to be useful months later.
        tags: Optional extra tags (the 'insight' tag is always added).

    Returns:
        dict with the stored note record.
    """
    try:
        if not title or not content:
            return {"status": "error", "error": "title and content are required"}
        note = Note(
            id=str(uuid4()),
            title=title,
            content=content,
            tags=normalize_tags([INSIGHT_TAG, *(tags or [])]),
        )
        with get_session() as session:
            session.add(note)
            session.commit()
            stored = note.to_dict()
        return {"status": "success", "insight": stored}
    except Exception as e:
        logger.error("save_insight failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def get_insights(
    query: Optional[str] = None, limit: int = DEFAULT_INSIGHTS_LIMIT
) -> Dict[str, Any]:
    """Retrieve saved insights, newest first, optionally filtered by text.

    Args:
        query: Optional case-insensitive substring filter on title and content.
        limit: Maximum insights to return (default: 20, max: 100).

    Returns:
        dict with the matching insight notes.
    """
    try:
        limit = max(1, min(int(limit), MAX_INSIGHTS_LIMIT))
        with get_session() as session:
            notes = (
                session.query(Note)
                .order_by(Note.created_at.desc())
                .limit(limit * NOTE_FETCH_MULTIPLIER)
                .all()
            )
            records = [n.to_dict() for n in notes]

        insights = [r for r in records if INSIGHT_TAG in (r.get("tags") or [])]
        if query:
            needle = query.lower()
            insights = [
                r
                for r in insights
                if needle in (r.get("title") or "").lower()
                or needle in (r.get("content") or "").lower()
            ]
        return {
            "status": "success",
            "count": len(insights[:limit]),
            "insights": insights[:limit],
        }
    except Exception as e:
        logger.error("get_insights failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
