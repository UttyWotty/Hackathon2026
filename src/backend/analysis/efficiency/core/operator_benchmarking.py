"""
Operator Benchmarking via Duration Behavioral Analysis.

This module detects operator shift patterns by analyzing temporal gaps in cycle
time data, benchmarks equipment performance across production sessions, and
identifies warmup penalties after production-end breaks (>8 hours).
"""

import logging
from typing import Dict, List

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ..models import (
    MIN_SHOTS_PER_SESSION,
    PRODUCTION_END_BREAK_HOURS,
    WARMUP_SHOT_COUNT,
    OperatorBenchmark,
    OperatorShiftPattern,
    classify_supplier_tier,
)
from .break_schedule_detector import analyze_intra_session_breaks

logger = logging.getLogger(__name__)


# ==================== Session Detection ==================== #


def detect_production_sessions(
    equipment_df: pd.DataFrame,
) -> List[pd.DataFrame]:
    """Split a single equipment's shot data into production sessions.

    A production session ends when the gap between consecutive shots exceeds
    PRODUCTION_END_BREAK_HOURS (8 hours). Only sessions with at least
    MIN_SHOTS_PER_SESSION (100) shots are kept as valid sessions.

    Args:
        equipment_df: DataFrame sorted by SHOT_TIME for one equipment

    Returns:
        List of DataFrames, each representing one valid production session
    """
    if len(equipment_df) < 2:
        return []

    df = equipment_df.sort_values("SHOT_TIME").copy()
    df["time_gap_hours"] = df["SHOT_TIME"].diff().dt.total_seconds() / 3600.0

    boundary_mask = df["time_gap_hours"] > PRODUCTION_END_BREAK_HOURS
    df["session_id"] = boundary_mask.cumsum()

    sessions = [
        group
        for _, group in df.groupby("session_id")
        if len(group) >= MIN_SHOTS_PER_SESSION
    ]

    return sessions


# ==================== Warmup Analysis ==================== #


def calculate_warmup_penalty(
    sessions: List[pd.DataFrame],
    production_end_indices: List[int],
) -> float:
    """Calculate efficiency penalty for first shots after a production-end break.

    Compares the efficiency of the first WARMUP_SHOT_COUNT shots in a session
    (that follows a >8h break) against the session's steady-state efficiency.

    Args:
        sessions: List of session DataFrames with efficiency_pct column
        production_end_indices: Indices of sessions that follow a >8h gap

    Returns:
        Average warmup penalty as a percentage (positive = worse than steady)
    """
    penalties = []

    for idx in production_end_indices:
        if idx >= len(sessions):
            continue
        session = sessions[idx]
        if len(session) < WARMUP_SHOT_COUNT * 2:
            continue

        warmup_eff = session["efficiency_pct"].iloc[:WARMUP_SHOT_COUNT].mean()
        steady_eff = session["efficiency_pct"].iloc[WARMUP_SHOT_COUNT:].mean()

        if not np.isnan(warmup_eff) and not np.isnan(steady_eff):
            penalty = steady_eff - warmup_eff
            penalties.append(penalty)

    if not penalties:
        return 0.0

    return float(np.mean(penalties))


# ==================== Shift Pattern Detection ==================== #


def detect_shift_patterns(
    df: pd.DataFrame,
    machine_id: str,
) -> OperatorShiftPattern:
    """Analyze one equipment's data to detect operator shift patterns.

    Args:
        df: DataFrame filtered to one equipment, with SHOT_TIME and
            efficiency_pct columns
        machine_id: The equipment identifier

    Returns:
        OperatorShiftPattern describing detected behavioral patterns
    """
    process_type = _get_first_value(df, "TYPE", "Unknown")

    sessions = detect_production_sessions(df)
    total_sessions = len(sessions)

    production_end_indices = list(range(1, total_sessions))
    production_end_count = len(production_end_indices)

    avg_break, has_planned, runs_nonstop, break_schedule = analyze_intra_session_breaks(
        sessions, total_sessions
    )

    session_durations = []
    shots_per_session_list = []
    for session in sessions:
        duration = (
            session["SHOT_TIME"].max() - session["SHOT_TIME"].min()
        ).total_seconds() / 3600.0
        session_durations.append(duration)
        shots_per_session_list.append(len(session))

    avg_duration = float(np.mean(session_durations)) if session_durations else 0.0
    avg_shots = (
        float(np.mean(shots_per_session_list)) if shots_per_session_list else 0.0
    )

    warmup_penalty = calculate_warmup_penalty(sessions, production_end_indices)

    return OperatorShiftPattern(
        machine_id=machine_id,
        process_type=process_type,
        total_sessions=total_sessions,
        avg_session_duration_hours=round(avg_duration, 2),
        avg_break_duration_hours=round(avg_break, 2),
        production_end_count=production_end_count,
        has_planned_downtime=has_planned,
        runs_nonstop=runs_nonstop,
        avg_warmup_penalty_pct=round(warmup_penalty, 2),
        shots_per_session=round(avg_shots, 1),
        break_schedule=break_schedule,
    )


# ==================== Operator Benchmarking ==================== #


def benchmark_operators(
    df: pd.DataFrame,
) -> List[OperatorBenchmark]:
    """Benchmark equipment performance at operator level using session analysis.

    Groups data by equipment, splits into sessions (>=100 shots each), and
    evaluates within-session and cross-session consistency.

    Args:
        df: Full DataFrame with efficiency_pct, tool_id, SHOT_TIME,
            TYPE, VENDOR_NAME columns

    Returns:
        List of OperatorBenchmark results sorted by rank
    """
    logger.info("Performing operator benchmarking analysis...")

    benchmarks = []
    equipment_groups = df.groupby("tool_id")

    for machine_id, equip_df in equipment_groups:
        equip_df = equip_df.sort_values("SHOT_TIME")
        process_type = _get_first_value(equip_df, "TYPE", "Unknown")
        vendor_name = _get_first_value(equip_df, "VENDOR_NAME", "Unknown")

        sessions = detect_production_sessions(equip_df)
        if len(sessions) < 1:
            continue

        mean_eff = float(equip_df["efficiency_pct"].mean())
        within_consistency = _calculate_within_session_consistency(sessions)
        cross_consistency = _calculate_cross_session_consistency(sessions)

        production_end_indices = list(range(1, len(sessions)))
        warmup_impact = calculate_warmup_penalty(sessions, production_end_indices)

        benchmark = OperatorBenchmark(
            machine_id=str(machine_id),
            process_type=process_type,
            vendor_name=vendor_name,
            session_count=len(sessions),
            mean_efficiency_pct=round(mean_eff, 2),
            within_session_consistency=round(within_consistency, 2),
            cross_session_consistency=round(cross_consistency, 2),
            warmup_impact_pct=round(warmup_impact, 2),
            performance_rank=0,
            tier_classification="",
            adjusted_score=0.0,
        )
        benchmarks.append(benchmark)

    benchmarks = _rank_operator_benchmarks(benchmarks)
    benchmarks = _assign_operator_tiers(benchmarks)

    logger.info("Benchmarked %d equipment for operator analysis", len(benchmarks))

    return benchmarks


# ==================== Helpers ==================== #


def _get_first_value(df: pd.DataFrame, column: str, default: str) -> str:
    """Safely get first value from a DataFrame column."""
    if column in df.columns and len(df) > 0:
        return str(df[column].iloc[0])
    return default


def _calculate_within_session_consistency(
    sessions: List[pd.DataFrame],
) -> float:
    """Calculate average within-session consistency across sessions.

    Args:
        sessions: List of session DataFrames with efficiency_pct

    Returns:
        Consistency score 0-100
    """
    cvs = []
    for session in sessions:
        eff = session["efficiency_pct"]
        mean_val = eff.mean()
        std_val = eff.std()
        if mean_val != 0 and not np.isnan(std_val):
            cv = (std_val / abs(mean_val)) * 100
            cvs.append(cv)

    if not cvs:
        return 50.0

    avg_cv = float(np.mean(cvs))
    return max(0.0, min(100.0, 100.0 - (avg_cv * 2)))


def _calculate_cross_session_consistency(
    sessions: List[pd.DataFrame],
) -> float:
    """Calculate consistency of mean efficiency across sessions.

    Args:
        sessions: List of session DataFrames with efficiency_pct

    Returns:
        Consistency score 0-100
    """
    session_means = [float(s["efficiency_pct"].mean()) for s in sessions]

    if len(session_means) < 2:
        return 50.0

    mean_val = float(np.mean(session_means))
    std_val = float(np.std(session_means))

    if mean_val == 0:
        return 0.0

    cv = (std_val / abs(mean_val)) * 100
    return max(0.0, min(100.0, 100.0 - (cv * 2)))


def _rank_operator_benchmarks(
    benchmarks: List[OperatorBenchmark],
) -> List[OperatorBenchmark]:
    """Rank operator benchmarks by adjusted score.

    Adjusted score: 50% efficiency + 25% within-session + 25% cross-session.

    Args:
        benchmarks: List of OperatorBenchmark objects

    Returns:
        Ranked list (best first)
    """
    for b in benchmarks:
        adjusted = (
            0.50 * b.mean_efficiency_pct
            + 0.25 * b.within_session_consistency
            + 0.25 * b.cross_session_consistency
        )
        b.adjusted_score = round(adjusted, 4)

    benchmarks.sort(key=lambda x: x.adjusted_score, reverse=True)

    for rank, b in enumerate(benchmarks, start=1):
        b.performance_rank = rank

    return benchmarks


def _assign_operator_tiers(
    benchmarks: List[OperatorBenchmark],
) -> List[OperatorBenchmark]:
    """Assign tier classifications to operator benchmarks.

    Args:
        benchmarks: Ranked list of OperatorBenchmark objects

    Returns:
        List with tier_classification populated
    """
    scores = [b.adjusted_score for b in benchmarks]
    if not scores:
        return benchmarks

    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score if max_score > min_score else 1.0

    for b in benchmarks:
        normalized = (b.adjusted_score - min_score) / score_range
        b.tier_classification = classify_supplier_tier(normalized)

    return benchmarks


def generate_operator_summary(
    benchmarks: List[OperatorBenchmark],
    shift_patterns: List[OperatorShiftPattern],
) -> Dict:
    """Generate summary statistics for operator benchmarking.

    Args:
        benchmarks: List of OperatorBenchmark results
        shift_patterns: List of OperatorShiftPattern detections

    Returns:
        Summary dictionary with aggregate stats
    """
    if not benchmarks:
        return {"total_equipment": 0}

    tier_counts: Dict[str, int] = {}
    for b in benchmarks:
        tier_counts[b.tier_classification] = (
            tier_counts.get(b.tier_classification, 0) + 1
        )

    efficiencies = [b.mean_efficiency_pct for b in benchmarks]
    warmups = [b.warmup_impact_pct for b in benchmarks]

    nonstop_count = sum(1 for s in shift_patterns if s.runs_nonstop)
    planned_count = sum(1 for s in shift_patterns if s.has_planned_downtime)

    return {
        "total_equipment": len(benchmarks),
        "tier_distribution": tier_counts,
        "mean_efficiency_pct": round(float(np.mean(efficiencies)), 2),
        "mean_warmup_impact_pct": round(float(np.mean(warmups)), 2),
        "equipment_running_nonstop": nonstop_count,
        "equipment_with_planned_downtime": planned_count,
        "top_equipment": {
            "code": benchmarks[0].machine_id,
            "efficiency": benchmarks[0].mean_efficiency_pct,
            "tier": benchmarks[0].tier_classification,
        },
        "bottom_equipment": {
            "code": benchmarks[-1].machine_id,
            "efficiency": benchmarks[-1].mean_efficiency_pct,
            "tier": benchmarks[-1].tier_classification,
        },
    }
