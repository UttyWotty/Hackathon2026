"""Data freshness classification for tables and pipeline outputs.

Classifies a data source as fresh, stale, or dead from the age of its newest record
versus the expected refresh cadence, with a dead multiplier for long-abandoned sources.
Pure logic: callers supply the last-data timestamp and the reference now.
"""

from datetime import datetime
from typing import Any, Dict, Optional

STATUS_FRESH: str = "fresh"
STATUS_STALE: str = "stale"
STATUS_DEAD: str = "dead"
STATUS_NO_DATA: str = "no_data"

DEAD_AGE_MULTIPLIER: float = 3.0
SECONDS_PER_HOUR: float = 3600.0
AGE_PRECISION: int = 1


def age_hours(last_time: Optional[datetime], now: datetime) -> Optional[float]:
    """Age of the newest record in hours, or None when there is no record."""
    if last_time is None:
        return None
    return round((now - last_time).total_seconds() / SECONDS_PER_HOUR, AGE_PRECISION)


def classify_freshness(
    data_age_hours: Optional[float], expected_max_age_hours: float
) -> str:
    """Classify a source from its data age and expected cadence.

    Args:
        data_age_hours: Hours since the newest record (None when no data exists).
        expected_max_age_hours: Maximum age considered fresh for this source.

    Returns:
        One of fresh, stale, dead, no_data. Dead means the age exceeds the
        expected maximum by DEAD_AGE_MULTIPLIER.
    """
    if data_age_hours is None:
        return STATUS_NO_DATA
    if data_age_hours <= expected_max_age_hours:
        return STATUS_FRESH
    if data_age_hours <= expected_max_age_hours * DEAD_AGE_MULTIPLIER:
        return STATUS_STALE
    return STATUS_DEAD


def build_freshness_entry(
    source: str,
    last_time: Optional[datetime],
    now: datetime,
    expected_max_age_hours: float,
) -> Dict[str, Any]:
    """Build the full freshness record for one source.

    Args:
        source: Source name (table or pipeline).
        last_time: Timestamp of the newest record (None when empty).
        now: Reference time for the age calculation.
        expected_max_age_hours: Maximum age considered fresh.

    Returns:
        dict with source, last_data_time, age_hours, expected_max_age_hours, status.
    """
    age = age_hours(last_time, now)
    return {
        "source": source,
        "last_data_time": last_time.isoformat() if last_time else None,
        "age_hours": age,
        "expected_max_age_hours": expected_max_age_hours,
        "status": classify_freshness(age, expected_max_age_hours),
    }
