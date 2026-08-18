"""
Tooling EOL Predictor.

This module contains the core end-of-life prediction logic for tooling,
including confidence scoring and maintenance integration.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from ..models.config import (
    CONFIDENCE_HIGH_WEEKS,
    CONFIDENCE_LOW_WEEKS,
    CONFIDENCE_MEDIUM_WEEKS,
    ELCPrediction,
    get_design_life,
)
from .data_loader import ensure_time_column, normalize_columns
from .rate_calculator import (
    calculate_weekly_rate,
    count_active_months,
    detect_seasonality,
)
from .utilization_analyzer import (
    categorize_utilization,
    compute_capacity_and_utilization,
)

# Configure logging
logger = logging.getLogger(__name__)


# ==================== Helper Functions ==================== #


def calculate_confidence_from_history(num_weeks: int) -> str:
    """Heuristic confidence based on number of weeks with activity.

    Args:
        num_weeks: Number of active weeks in history

    Returns:
        str: Confidence level ('High', 'Medium', 'Low', or 'Very Low')
    """
    if num_weeks >= CONFIDENCE_HIGH_WEEKS:
        return "High"
    if num_weeks >= CONFIDENCE_MEDIUM_WEEKS:
        return "Medium"
    if num_weeks >= CONFIDENCE_LOW_WEEKS:
        return "Low"
    return "Very Low"


# ==================== EOL Prediction ==================== #


def predict_end_of_life_for_mold(
    mold_df: pd.DataFrame,
    bins: Iterable[int] = (0, 30, 80, 100),
    maintenance_events: Optional[pd.DataFrame] = None,
) -> ELCPrediction:
    """Compute end-of-life metrics for a single mold dataframe.

    Args:
        mold_df: Dataframe containing only one mold's rows.
        bins: Utilization bins for categorization.
        maintenance_events: Optional DataFrame with maintenance history.

    Returns:
        ELCPrediction: Structured prediction result.

    Raises:
        ValueError: If mold_df is empty
    """
    if mold_df.empty:
        raise ValueError("mold_df must contain at least one row for a specific mold")

    tool_id = int(mold_df["TOOL_ID"].iloc[0]) if "TOOL_ID" in mold_df.columns else -1
    # TYPE may be null/empty; leave type_category None so downstream
    # config lookups fall back to their defaults instead of failing.
    type_category = None
    if "TYPE" in mold_df.columns and mold_df["TYPE"].notna().any():
        type_category = str(mold_df["TYPE"].dropna().mode().iloc[0])

    machine_id = None
    if "MACHINE_ID" in mold_df.columns and mold_df["MACHINE_ID"].notna().any():
        machine_id = str(mold_df["MACHINE_ID"].dropna().mode().iloc[0])

    # Build weekly series
    tmp = mold_df.dropna(subset=["SHOT_TIME"]).copy()
    tmp["WEEK_START"] = tmp["SHOT_TIME"].dt.to_period("W-MON").dt.start_time
    weekly_series = (
        tmp.groupby("WEEK_START")["SHOT_COUNT"].sum().replace(0, np.nan).dropna()
    ).sort_index()

    w_rate = calculate_weekly_rate(mold_df)
    ideal_capacity, util_pct = compute_capacity_and_utilization(mold_df, w_rate)
    util_category = categorize_utilization(util_pct, bins=bins)

    # Prefer designed shot from MOLD when available; else family mapping
    design_life = None
    if "DESIGNED_SHOT" in mold_df.columns and mold_df["DESIGNED_SHOT"].notna().any():
        try:
            design_life = int(float(mold_df["DESIGNED_SHOT"].dropna().median()))
        except Exception:
            design_life = None
    if not design_life:
        design_life = get_design_life(type_category)

    # Current shots observed in available data (may be a partial lifetime window)
    current_shots = int(mold_df.shape[0])

    # Maintenance reset (optional): if MAINTENANCE table exists and has refurbishment
    refurb_ts = None
    maintenance_applied = False
    maintenance_source = None
    maintenance_warning = None
    candidate_refurb_dates: list[str] = []

    # Use maintenance_events if provided: pick latest event before latest shot
    if maintenance_events is not None and not maintenance_events.empty:
        me = maintenance_events[maintenance_events["TOOL_ID"] == tool_id]
        if not me.empty:
            me_sorted = me.sort_values("EVENT_TS")
            latest_event = me_sorted["EVENT_TS"].max()
            if pd.notna(latest_event):
                refurb_ts = pd.to_datetime(latest_event)
                maintenance_applied = True
                # Determine source of latest event
                src = me_sorted[me_sorted["EVENT_TS"] == latest_event]["SOURCE"]
                if not src.empty:
                    maintenance_source = str(src.iloc[0])
        else:
            maintenance_warning = "No maintenance events for mold"
    else:
        maintenance_warning = "Maintenance data missing — EOL may be pessimistic"

    # Heuristic candidate refurb dates from shot gaps (for future audits)
    if weekly_series is not None and not weekly_series.empty:
        # find gaps > 28 days between consecutive week starts
        gaps = weekly_series.index.to_series().diff().dt.days
        gap_dates = weekly_series.index[gaps >= 28]
        candidate_refurb_dates = [
            pd.to_datetime(d).date().isoformat() for d in gap_dates[-3:]
        ]

    # If refurb timestamp available, reset shots since refurb
    if refurb_ts is not None:
        shots_since_refurb = mold_df[mold_df["SHOT_TIME"] >= refurb_ts].shape[0]
        current_shots = int(shots_since_refurb)

    # Seasonal horizon adjustment: scale weekly rate if flagged seasonal
    seasonal_flag = detect_seasonality(weekly_series)
    if seasonal_flag:
        active_months = count_active_months(weekly_series, months_window=12)
        scale = max(0.1, min(1.0, active_months / 12.0))
        w_rate_for_horizon = max(0.0, w_rate * scale)
    else:
        w_rate_for_horizon = w_rate

    # Remaining shots & days (bias to most recent trend: use last 4 active weeks if available)
    if weekly_series is not None and weekly_series.size >= 4:
        last4 = weekly_series.iloc[-4:]
        # Weighted average over last 4 (1..4)
        weights4 = np.arange(1, len(last4) + 1, dtype=float)
        try:
            w_rate_recent = float(np.average(last4.values, weights=weights4))
        except ZeroDivisionError:
            w_rate_recent = float(last4.mean())
        # Take the max of scaled seasonal and recent-4 to avoid overreacting to tiny blips
        horizon_rate = max(0.0, max(w_rate_for_horizon, w_rate_recent))
    else:
        horizon_rate = w_rate_for_horizon

    # Remaining shots & days
    remaining_shots = max(design_life - current_shots, 0)
    if horizon_rate > 0:
        remaining_weeks = remaining_shots / horizon_rate
        remaining_days = float(remaining_weeks * 7.0)
    else:
        remaining_days = np.inf

    latest_ts = None
    if "SHOT_TIME" in mold_df.columns:
        latest_ts = pd.to_datetime(mold_df["SHOT_TIME"].max())

    # Baseline for projection: use the later of latest shot time and today
    baseline_ts = None
    now_ts = pd.Timestamp.now()
    if latest_ts is not None:
        baseline_ts = latest_ts if latest_ts > now_ts else now_ts
    else:
        baseline_ts = now_ts

    if baseline_ts is not None and np.isfinite(remaining_days):
        predicted_date = baseline_ts + pd.Timedelta(days=remaining_days)
    else:
        predicted_date = pd.NaT

    # Confidence: based on number of active weeks with shot activity
    num_weeks_active = (
        mold_df.dropna(subset=["SHOT_TIME"])
        .assign(WEEK=lambda d: d["SHOT_TIME"].dt.strftime("%G%V"))["WEEK"]
        .nunique()
    )
    confidence = calculate_confidence_from_history(int(num_weeks_active))

    # Confidence percent from multiple signals
    # 1) History coverage (cap 26 weeks)
    history_score = min(num_weeks_active / 26.0, 1.0)
    # 2) Recency of last shot (90-day horizon)
    days_since_last = (
        float((pd.Timestamp.now() - latest_ts).days)
        if latest_ts is not None
        else 9999.0
    )
    recency_score = max(0.0, min(1.0, 1.0 - (days_since_last / 90.0)))
    # 3) Stability: coefficient of variation of weekly shots (lower is better)
    if (
        weekly_series is not None
        and weekly_series.size >= 3
        and weekly_series.mean() > 0
    ):
        cv = float(weekly_series.std(ddof=0) / weekly_series.mean())
        stability_score = max(0.0, min(1.0, 1.0 - min(cv, 2.0) / 2.0))
    else:
        stability_score = 0.3

    base_conf = (history_score + recency_score + stability_score) / 3.0
    if seasonal_flag:
        base_conf *= 0.8
    confidence_pct = round(base_conf * 100.0, 1)
    history_coverage_pct = round(history_score * 100.0, 1)
    recency_pct = round(recency_score * 100.0, 1)
    stability_pct = round(stability_score * 100.0, 1)

    # Overutilization streak detection
    over_streak = None
    warnings_list = []
    if (
        ideal_capacity
        and ideal_capacity > 0
        and weekly_series is not None
        and not weekly_series.empty
    ):
        # Determine high threshold from bins (use lower bound of 'High')
        b0, b1, b2, b3 = list(bins)
        # Compute weekly utilization values (percent)
        weekly_util = (weekly_series / ideal_capacity) * 100.0
        # Build streak of consecutive weeks above high_threshold
        streak = 0
        max_streak = 0
        for val in weekly_util.values:
            if np.isfinite(val) and val > b2:  # above 'High' lower bound
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        over_streak = int(max_streak)
        if over_streak >= 4:
            warnings_list.append(
                "Overutilization > High for >=4 weeks; early inspection suggested"
            )

    # Life consumption percent (how much of design life used)
    life_consumption_pct = None
    if design_life and design_life > 0:
        life_consumption_pct = float((current_shots / design_life) * 100.0)

    return ELCPrediction(
        tool_id=tool_id,
        machine_id=machine_id,
        latest_shot_time=latest_ts,
        current_shots_observed=current_shots,
        weekly_rate=float(w_rate),
        ideal_weekly_capacity=(
            float(ideal_capacity) if np.isfinite(ideal_capacity) else None
        ),
        utilization_pct=float(util_pct) if np.isfinite(util_pct) else None,
        utilization_category=util_category,
        design_shot_life=int(design_life),
        life_consumption_pct=life_consumption_pct,
        remaining_shots=int(remaining_shots),
        remaining_days=float(remaining_days) if np.isfinite(remaining_days) else None,
        predicted_eol_date=(
            pd.to_datetime(predicted_date) if not pd.isna(predicted_date) else None
        ),
        confidence=confidence,
        confidence_pct=confidence_pct,
        seasonal_flag=bool(seasonal_flag),
        overutilization_weeks_streak=over_streak,
        warnings=", ".join(warnings_list) if warnings_list else None,
        # Maintenance diagnostics
        maintenance_applied=maintenance_applied,
        maintenance_date=pd.to_datetime(refurb_ts) if refurb_ts is not None else None,
        maintenance_source=maintenance_source,
        maintenance_warning=maintenance_warning,
        candidate_refurb_dates=(
            ", ".join(candidate_refurb_dates) if candidate_refurb_dates else None
        ),
        history_coverage_pct=history_coverage_pct,
        recency_pct=recency_pct,
        stability_pct=stability_pct,
    )


def predict_end_of_life(
    df: pd.DataFrame,
    bins: Iterable[int] = (0, 30, 80, 100),
    maintenance_events: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Run EOL prediction for all molds present in the dataframe.

    Args:
        df: SHOT_DATA DataFrame.
        bins: Utilization bins for categorization.
        maintenance_events: Optional DataFrame with maintenance history.

    Returns:
        pd.DataFrame: One row per mold with EOL metrics.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "TOOL_ID",
                "LATEST_SHOT_TIME",
                "CURRENT_SHOTS_OBSERVED",
                "WEEKLY_RATE",
                "IDEAL_WEEKLY_CAPACITY",
                "UTILIZATION_PCT",
                "UTILIZATION_CATEGORY",
                "DESIGN_SHOT_LIFE",
                "REMAINING_SHOTS",
                "REMAINING_DAYS",
                "PREDICTED_EOL_DATE",
                "CONFIDENCE",
            ]
        )

    # Normalize incoming df to avoid KeyError on column casing
    df = normalize_columns(df)
    df = ensure_time_column(df)

    # Validate required column
    if "TOOL_ID" not in df.columns:
        raise KeyError(
            "Required column 'TOOL_ID' not found. Available columns: "
            + ", ".join(map(str, df.columns))
        )

    results: list[ELCPrediction] = []
    for tool_id, mold_df in df.groupby("TOOL_ID"):
        try:
            results.append(
                predict_end_of_life_for_mold(
                    mold_df, bins=bins, maintenance_events=maintenance_events
                )
            )
        except Exception as exc:
            logger.warning(f"Skipping tool_id={tool_id} due to error: {exc}")

    # Convert dataclass list to DataFrame
    out = pd.DataFrame([r.__dict__ for r in results])
    # Formatting
    if not out.empty:
        if "predicted_eol_date" in out.columns:
            out["predicted_eol_date"] = pd.to_datetime(
                out["predicted_eol_date"]
            ).dt.date
        if "latest_shot_time" in out.columns:
            out["latest_shot_time"] = pd.to_datetime(
                out["latest_shot_time"]
            )  # keep timezone-naive

        # Order / rename for clarity
        out = out.rename(
            columns={
                "machine_id": "MACHINE_ID",
                "latest_shot_time": "LATEST_SHOT_TIME",
                "current_shots_observed": "CURRENT_SHOTS_OBSERVED",
                "weekly_rate": "WEEKLY_RATE",
                "ideal_weekly_capacity": "IDEAL_WEEKLY_CAPACITY",
                "utilization_pct": "UTILIZATION_PCT",
                "utilization_category": "UTILIZATION_CATEGORY",
                "design_shot_life": "DESIGN_SHOT_LIFE",
                "life_consumption_pct": "LIFE_CONSUMPTION_PCT",
                "confidence_pct": "CONFIDENCE_PCT",
                "seasonal_flag": "SEASONAL_FLAG",
                "overutilization_weeks_streak": "OVERUTIL_WEEKS_STREAK",
                "warnings": "WARNINGS",
                "maintenance_applied": "MAINTENANCE_APPLIED",
                "maintenance_date": "MAINTENANCE_DATE",
                "maintenance_source": "MAINTENANCE_SOURCE",
                "maintenance_warning": "MAINTENANCE_WARNING",
                "candidate_refurb_dates": "CANDIDATE_REFURB_DATES",
                "history_coverage_pct": "HISTORY_COVERAGE_PCT",
                "recency_pct": "RECENCY_PCT",
                "stability_pct": "STABILITY_PCT",
                "remaining_shots": "REMAINING_SHOTS",
                "remaining_days": "REMAINING_DAYS",
                "predicted_eol_date": "PREDICTED_EOL_DATE",
                "confidence": "CONFIDENCE",
            }
        )

        # Round numeric columns to 2 decimals for readability
        for col in [
            "WEEKLY_RATE",
            "IDEAL_WEEKLY_CAPACITY",
            "UTILIZATION_PCT",
            "LIFE_CONSUMPTION_PCT",
            "CONFIDENCE_PCT",
            "REMAINING_DAYS",
        ]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").round(2)

        # Sort by soonest EOL first using date value, then MACHINE_ID
        out = out.sort_values(
            by=["PREDICTED_EOL_DATE", "MACHINE_ID"], na_position="last"
        )

    return out
