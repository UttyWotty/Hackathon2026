"""
Risk Tower Analysis Module
==========================

Calculates risk metrics for equipment over a rolling 4-week window.
Includes trend analysis, risk scoring, and primary risk factor identification.
"""

from typing import Tuple

import pandas as pd

# Risk thresholds
STABILITY_CRITICAL = 50.0  # Red status threshold
STABILITY_MODERATE = 70.0  # Orange status threshold
TREND_DECLINE_THRESHOLD = 0.05  # 5% relative decline triggers trend flag
TREND_PENALTY_POINTS = 20  # Points deducted for declining trend
HIGH_MTTR_MULTIPLIER = 1.2  # MTTR > 1.2x avg is "High MTTR"
LOW_MTBF_MULTIPLIER = 0.8  # MTBF < 0.8x avg is "Frequent Stops"


def calculate_weekly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate weekly metrics per equipment for Risk Tower analysis.

    Groups data by equipment and ISO week, then calculates:
    - Stability Index (% of run time in normal production)
    - Total production time, downtime
    - Stop events count
    - MTTR and MTBF

    Args:
        df: Processed DataFrame with session metrics

    Returns:
        DataFrame with weekly aggregated metrics per equipment
    """
    if df.empty:
        return pd.DataFrame()

    # Ensure we have the timestamp column
    if "LOCAL_SHOT_TIME" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])
    df["ISO_WEEK"] = df["LOCAL_SHOT_TIME"].dt.isocalendar().week
    df["ISO_YEAR"] = df["LOCAL_SHOT_TIME"].dt.isocalendar().year
    df["YEAR_WEEK"] = (
        df["ISO_YEAR"].astype(str) + "-W" + df["ISO_WEEK"].astype(str).str.zfill(2)
    )

    # Group by equipment and week
    weekly_metrics = []

    for (equipment, year_week), group in df.groupby(["EQUIPMENT_CODE", "YEAR_WEEK"]):
        # Get the first row's session metrics (they're the same for all rows in session)
        # For multi-session weeks, we need to aggregate properly
        sessions = group.groupby("SESSION_ID").first()

        total_prod_time = (
            sessions["PRODUCTION_TIME"].sum()
            if "PRODUCTION_TIME" in sessions.columns
            else 0
        )
        total_run_time = (
            sessions["TOTAL_RUN_TIME"].sum()
            if "TOTAL_RUN_TIME" in sessions.columns
            else 0
        )
        total_down_time = (
            sessions["TOTAL_DOWN_TIME"].sum()
            if "TOTAL_DOWN_TIME" in sessions.columns
            else 0
        )
        total_stops = (
            sessions["TOTAL_STOPS"].sum() if "TOTAL_STOPS" in sessions.columns else 0
        )

        # Calculate Stability Index for the week
        stability_index = (
            (total_prod_time / total_run_time * 100) if total_run_time > 0 else 0
        )

        # Calculate MTTR and MTBF for the week
        mttr = (total_down_time / total_stops) if total_stops > 0 else 0
        mtbf = (total_prod_time / total_stops) if total_stops > 0 else 0

        weekly_metrics.append(
            {
                "EQUIPMENT_CODE": equipment,
                "YEAR_WEEK": year_week,
                "ISO_YEAR": group["ISO_YEAR"].iloc[0],
                "ISO_WEEK": group["ISO_WEEK"].iloc[0],
                "STABILITY_INDEX": round(stability_index, 1),
                "PRODUCTION_TIME": total_prod_time,
                "TOTAL_RUN_TIME": total_run_time,
                "TOTAL_DOWN_TIME": total_down_time,
                "STOP_EVENTS": total_stops,
                "MTTR": round(mttr, 2),
                "MTBF": round(mtbf, 2),
                "SHOT_COUNT": len(group),
            }
        )

    return pd.DataFrame(weekly_metrics)


def calculate_trend(
    weekly_df: pd.DataFrame, equipment_code: str
) -> Tuple[float, float, bool]:
    """
    Calculate trend for an equipment over the analysis window.

    Compares First Active Week vs Last Active Week stability index.
    Weeks with zero production are ignored.

    Args:
        weekly_df: Weekly metrics DataFrame
        equipment_code: Equipment to analyze

    Returns:
        Tuple of (first_week_stability, last_week_stability, is_declining)
    """
    equip_data = weekly_df[weekly_df["EQUIPMENT_CODE"] == equipment_code].copy()

    if equip_data.empty:
        return 0.0, 0.0, False

    # Sort by year and week
    equip_data = equip_data.sort_values(["ISO_YEAR", "ISO_WEEK"])

    # Filter to only weeks with actual production (stability > 0)
    active_weeks = equip_data[equip_data["STABILITY_INDEX"] > 0]

    if len(active_weeks) < 2:
        # Not enough data to calculate trend
        if len(active_weeks) == 1:
            stability = active_weeks["STABILITY_INDEX"].iloc[0]
            return stability, stability, False
        return 0.0, 0.0, False

    first_week_stability = active_weeks["STABILITY_INDEX"].iloc[0]
    last_week_stability = active_weeks["STABILITY_INDEX"].iloc[-1]

    # Calculate relative decline
    if first_week_stability > 0:
        relative_change = (
            first_week_stability - last_week_stability
        ) / first_week_stability
        is_declining = relative_change > TREND_DECLINE_THRESHOLD
    else:
        is_declining = False

    return first_week_stability, last_week_stability, is_declining


def calculate_risk_score(stability_index: float, is_declining: bool) -> int:
    """
    Calculate Risk Score for equipment (0-100 scale).

    Base Score = Stability Index
    Penalty: -20 points if declining trend detected

    Args:
        stability_index: Overall stability index for the period
        is_declining: Whether trend is declining

    Returns:
        Risk score (0-100, lower = higher risk)
    """
    base_score = stability_index

    if is_declining:
        base_score -= TREND_PENALTY_POINTS

    # Clamp to 0-100 range
    return max(0, min(100, int(round(base_score))))


def get_primary_risk_factor(
    stability_index: float,
    is_declining: bool,
    mttr: float,
    mtbf: float,
    avg_mttr: float,
    avg_mtbf: float,
) -> str:
    """
    Determine the Primary Risk Factor for equipment.

    Priority order:
    1. "Declining Trend" - if trend penalty was applied
    2. "High MTTR" - if Stability < 70% AND MTTR > 1.2× avg
    3. "Frequent Stops" - if Stability < 70% AND MTBF < 0.8× avg
    4. "Critical Stability" - if Stability < 50% (Red)
    5. "Moderate Stability" - if 50% ≤ Stability < 70% (Orange)
    6. "Stable" - if Stability ≥ 70% (Green)

    Args:
        stability_index: Overall stability index
        is_declining: Whether trend is declining
        mttr: Equipment's MTTR
        mtbf: Equipment's MTBF
        avg_mttr: Average MTTR across all equipment
        avg_mtbf: Average MTBF across all equipment

    Returns:
        Primary risk factor string
    """
    # Priority 1: Declining Trend
    if is_declining:
        return "Declining Trend"

    # Priority 2 & 3: High MTTR or Frequent Stops (only if stability < 70%)
    if stability_index < STABILITY_MODERATE:
        if avg_mttr > 0 and mttr > (HIGH_MTTR_MULTIPLIER * avg_mttr):
            return "High MTTR"
        if avg_mtbf > 0 and mtbf < (LOW_MTBF_MULTIPLIER * avg_mtbf):
            return "Frequent Stops"

    # Priority 4: Critical Stability (Red)
    if stability_index < STABILITY_CRITICAL:
        return "Critical Stability"

    # Priority 5: Moderate Stability (Orange)
    if stability_index < STABILITY_MODERATE:
        return "Moderate Stability"

    # Priority 6: Stable (Green)
    return "Stable"


def get_rag_status(stability_index: float) -> str:
    """
    Get RAG (Red/Amber/Green) status based on stability index.

    Args:
        stability_index: Stability index percentage

    Returns:
        "Red", "Amber", or "Green"
    """
    if stability_index < STABILITY_CRITICAL:
        return "Red"
    elif stability_index < STABILITY_MODERATE:
        return "Amber"
    return "Green"


def calculate_risk_tower(df: pd.DataFrame, weeks: int = 4) -> pd.DataFrame:
    """
    Calculate Risk Tower metrics for all equipment over rolling N-week window.

    This is the main entry point for Risk Tower analysis.

    Args:
        df: Processed DataFrame with session metrics
        weeks: Number of weeks for rolling window (default 4)

    Returns:
        DataFrame with Risk Tower data per equipment:
        - EQUIPMENT_CODE
        - STABILITY_INDEX (overall for period)
        - FIRST_WEEK_STABILITY
        - LAST_WEEK_STABILITY
        - IS_DECLINING
        - RISK_SCORE
        - PRIMARY_RISK_FACTOR
        - RAG_STATUS
        - MTTR, MTBF
        - STOP_EVENTS
        - PRODUCTION_TIME, TOTAL_RUN_TIME
    """
    if df.empty:
        return pd.DataFrame()

    # Calculate weekly metrics
    weekly_df = calculate_weekly_metrics(df)

    if weekly_df.empty:
        return pd.DataFrame()

    # Filter to last N weeks
    weekly_df = weekly_df.sort_values(["ISO_YEAR", "ISO_WEEK"])
    unique_weeks = weekly_df[["ISO_YEAR", "ISO_WEEK"]].drop_duplicates()
    if len(unique_weeks) > weeks:
        cutoff = unique_weeks.iloc[-weeks]
        weekly_df = weekly_df[
            (weekly_df["ISO_YEAR"] > cutoff["ISO_YEAR"])
            | (
                (weekly_df["ISO_YEAR"] == cutoff["ISO_YEAR"])
                & (weekly_df["ISO_WEEK"] >= cutoff["ISO_WEEK"])
            )
        ]

    # Calculate averages for MTTR and MTBF comparison
    avg_mttr = (
        weekly_df[weekly_df["MTTR"] > 0]["MTTR"].mean() if not weekly_df.empty else 0
    )
    avg_mtbf = (
        weekly_df[weekly_df["MTBF"] > 0]["MTBF"].mean() if not weekly_df.empty else 0
    )

    # Build Risk Tower data per equipment
    risk_tower_data = []

    for equipment in weekly_df["EQUIPMENT_CODE"].unique():
        equip_weekly = weekly_df[weekly_df["EQUIPMENT_CODE"] == equipment]

        # Aggregate metrics for the entire period
        total_prod_time = equip_weekly["PRODUCTION_TIME"].sum()
        total_run_time = equip_weekly["TOTAL_RUN_TIME"].sum()
        total_down_time = equip_weekly["TOTAL_DOWN_TIME"].sum()
        total_stops = equip_weekly["STOP_EVENTS"].sum()

        # Overall Stability Index for the period
        stability_index = (
            (total_prod_time / total_run_time * 100) if total_run_time > 0 else 0
        )

        # Calculate MTTR and MTBF for the period
        mttr = (total_down_time / total_stops) if total_stops > 0 else 0
        mtbf = (total_prod_time / total_stops) if total_stops > 0 else 0

        # Calculate trend
        first_week, last_week, is_declining = calculate_trend(weekly_df, equipment)

        # Calculate risk score
        risk_score = calculate_risk_score(stability_index, is_declining)

        # Determine primary risk factor
        primary_factor = get_primary_risk_factor(
            stability_index, is_declining, mttr, mtbf, avg_mttr, avg_mtbf
        )

        # Get RAG status
        rag_status = get_rag_status(stability_index)

        risk_tower_data.append(
            {
                "EQUIPMENT_CODE": equipment,
                "STABILITY_INDEX": round(stability_index, 1),
                "FIRST_WEEK_STABILITY": round(first_week, 1),
                "LAST_WEEK_STABILITY": round(last_week, 1),
                "TREND_CHANGE": round(last_week - first_week, 1),
                "IS_DECLINING": is_declining,
                "RISK_SCORE": risk_score,
                "PRIMARY_RISK_FACTOR": primary_factor,
                "RAG_STATUS": rag_status,
                "MTTR": round(mttr, 2),
                "MTBF": round(mtbf, 2),
                "STOP_EVENTS": total_stops,
                "PRODUCTION_TIME": round(total_prod_time, 2),
                "TOTAL_RUN_TIME": round(total_run_time, 2),
                "TOTAL_DOWN_TIME": round(total_down_time, 2),
                "WEEKS_ANALYZED": len(equip_weekly),
            }
        )

    # Create DataFrame and sort by risk score (lowest = highest risk first)
    result_df = pd.DataFrame(risk_tower_data)
    if not result_df.empty:
        result_df = result_df.sort_values("RISK_SCORE", ascending=True)

    return result_df
