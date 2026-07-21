"""
Break Schedule Detector for Operator Shift Analysis.

This module clusters intra-session break events by time-of-day to identify
recurring patterns such as coffee breaks, lunch breaks, and dinner breaks.
"""

import logging
from typing import Dict, List, Tuple

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ..models import (
    BREAK_CLUSTER_WINDOW_HOURS,
    MIN_SESSIONS_FOR_ANALYSIS,
    PLANNED_DOWNTIME_MIN_RATIO,
    PRODUCTION_END_BREAK_HOURS,
)

logger = logging.getLogger(__name__)


# ==================== Break Event Collection ==================== #


def collect_break_events(
    sessions: List[pd.DataFrame],
) -> List[Dict[str, object]]:
    """Collect all significant intra-session break events with timestamps.

    Significant breaks are gaps between 0.5 and 8 hours within a session.

    Args:
        sessions: List of session DataFrames with time_gap_hours column

    Returns:
        List of dicts with hour_of_day, duration_hours, and session_idx
    """
    breaks: List[Dict[str, object]] = []
    for session_idx, session_df in enumerate(sessions):
        mask = (session_df["time_gap_hours"] >= 0.5) & (
            session_df["time_gap_hours"] <= PRODUCTION_END_BREAK_HOURS
        )
        break_rows = session_df[mask]
        for _, row in break_rows.iterrows():
            hour_of_day = (
                row["LOCAL_SHOT_TIME"].hour + row["LOCAL_SHOT_TIME"].minute / 60.0
            )
            breaks.append(
                {
                    "hour_of_day": round(hour_of_day, 2),
                    "duration_hours": round(float(row["time_gap_hours"]), 2),
                    "session_idx": session_idx,
                }
            )
    return breaks


# ==================== Clustering ==================== #


def cluster_break_times(
    break_events: List[Dict[str, object]],
    total_sessions: int,
) -> List[Dict[str, object]]:
    """Cluster break events by time-of-day to detect recurring patterns.

    Groups breaks that happen within BREAK_CLUSTER_WINDOW_HOURS of each other.
    Only returns clusters that appear in at least PLANNED_DOWNTIME_MIN_RATIO
    of unique sessions.

    Args:
        break_events: List of break events with hour_of_day, duration_hours, session_idx
        total_sessions: Number of valid sessions (for ratio calculation)

    Returns:
        List of detected break clusters with label, avg time, frequency
    """
    if not break_events or total_sessions < MIN_SESSIONS_FOR_ANALYSIS:
        return []

    sorted_events = sorted(break_events, key=lambda x: x["hour_of_day"])

    clusters: List[List[Dict[str, object]]] = []
    current_cluster: List[Dict[str, object]] = []

    for event in sorted_events:
        if not current_cluster:
            current_cluster.append(event)
        elif (
            float(event["hour_of_day"]) - float(current_cluster[-1]["hour_of_day"])
            <= BREAK_CLUSTER_WINDOW_HOURS
        ):
            current_cluster.append(event)
        else:
            clusters.append(current_cluster)
            current_cluster = [event]

    if current_cluster:
        clusters.append(current_cluster)

    min_unique_sessions = max(1, int(total_sessions * PLANNED_DOWNTIME_MIN_RATIO))
    results = []

    for cluster in clusters:
        unique_sessions = len(set(b["session_idx"] for b in cluster))
        if unique_sessions < min_unique_sessions:
            continue

        avg_hour = float(np.mean([float(b["hour_of_day"]) for b in cluster]))
        avg_duration = float(np.mean([float(b["duration_hours"]) for b in cluster]))
        frequency_pct = round(unique_sessions / total_sessions * 100, 1)

        hour_int = int(avg_hour)
        minute_int = int((avg_hour - hour_int) * 60)
        time_str = f"{hour_int:02d}:{minute_int:02d}"

        label = classify_break_type(avg_hour, avg_duration)

        results.append(
            {
                "label": label,
                "avg_time": time_str,
                "avg_hour": round(avg_hour, 2),
                "avg_duration_hours": round(avg_duration, 2),
                "sessions_with_break": unique_sessions,
                "frequency_pct": frequency_pct,
            }
        )

    return results


# ==================== Classification ==================== #


def classify_break_type(hour: float, duration: float) -> str:
    """Classify a break cluster into a human-readable label.

    Args:
        hour: Average hour-of-day (0-24)
        duration: Average duration in hours

    Returns:
        Label string (e.g. 'Morning Break', 'Lunch Break')
    """
    if 5.0 <= hour < 10.0 and duration < 1.0:
        return "Morning Break"
    elif 10.0 <= hour < 14.0 and duration >= 0.5:
        return "Lunch Break"
    elif 14.0 <= hour < 17.0 and duration < 1.0:
        return "Afternoon Break"
    elif 17.0 <= hour < 21.0 and duration >= 0.5:
        return "Dinner Break"
    elif 21.0 <= hour or hour < 5.0:
        return "Night Break"
    return "Break"


# ==================== Combined Analysis ==================== #


def analyze_intra_session_breaks(
    sessions: List[pd.DataFrame],
    total_valid_sessions: int,
) -> Tuple[float, bool, bool, List[Dict[str, object]]]:
    """Analyze breaks within production sessions to detect operator patterns.

    Args:
        sessions: List of session DataFrames with time_gap_hours column
        total_valid_sessions: Number of valid sessions for ratio checks

    Returns:
        Tuple of (avg_break_hours, has_planned_downtime, runs_nonstop, break_schedule)
    """
    break_events = collect_break_events(sessions)

    if not break_events:
        return 0.0, False, True, []

    avg_break = float(np.mean([b["duration_hours"] for b in break_events]))

    break_schedule = cluster_break_times(break_events, total_valid_sessions)

    has_planned = len(break_schedule) > 0

    return avg_break, has_planned, False, break_schedule
