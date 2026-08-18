"""
Downtime detection and statistics for Pareto analysis on manufacturing shot data.
Provides standalone functions to calculate real downtime using company logic,
detect downtime events via timestamp gaps and CT spikes, and compute downtime statistics.
Used by ParetoAnalysis during the data preparation phase.
"""

from typing import Optional

import numpy as np
import pandas as pd

from analysis.shared.constants import SessionDetection

# ---------------------------------------------------------------------------
# Default thresholds (callers may override)
# ---------------------------------------------------------------------------
DOWNTIME_GAP_THRESHOLD: float = 5.0
DOWNTIME_DURATION_MULTIPLIER: float = 2.0

# Downtime rounding errors to ignore (seconds)
ROUNDING_ERRORS = {-1, 0, 1}

# Invalid duration sentinel
INVALID_CT_THRESHOLD: float = 999.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_real_downtime(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate real downtime using company logic: time between shots minus previous duration.

    Rules applied:
    - Skip when previous DURATION >= 999 (invalid).
    - Skip when gap exceeds SESSION_GAP_SECONDS (session break).
    - Ignore rounding errors (-1, 0, 1 seconds).
    - Only positive downtime is recorded.

    Args:
        df: Manufacturing shot data with SHOT_TIME and DURATION columns.

    Returns:
        The input DataFrame with TIME_BETWEEN_SHOTS and DOWNTIME columns added.
    """
    df = df.sort_values("SHOT_TIME")
    df["TIME_BETWEEN_SHOTS"] = df["SHOT_TIME"].diff().dt.total_seconds()
    df["DOWNTIME"] = 0.0

    for i in range(1, len(df)):
        time_between = df.iloc[i]["TIME_BETWEEN_SHOTS"]
        prev_ct = df.iloc[i - 1]["DURATION"]

        if prev_ct >= INVALID_CT_THRESHOLD:
            continue

        downtime = time_between - prev_ct

        if downtime > SessionDetection.SESSION_GAP_SECONDS:
            continue

        if downtime in ROUNDING_ERRORS:
            continue

        if downtime > 1:
            df.iloc[i, df.columns.get_loc("DOWNTIME")] = downtime

    _print_real_downtime_summary(df)
    return df


def detect_downtime_events(
    df: pd.DataFrame,
    gap_threshold: float = DOWNTIME_GAP_THRESHOLD,
    ct_multiplier: float = DOWNTIME_DURATION_MULTIPLIER,
) -> pd.DataFrame:
    """Detect downtime events using timestamp gaps and CT spikes.

    Args:
        df: Shot data with SHOT_TIME and DURATION columns.
        gap_threshold: Minimum gap in minutes to flag as downtime.
        ct_multiplier: Multiple of median CT above which a shot is a spike.

    Returns:
        DataFrame with TIME_GAP_MINUTES, DOWNTIME_GAP_FLAG,
        DOWNTIME_CT_FLAG, and DOWNTIME_EVENT columns.
    """
    print("\n  Detecting downtime events for equipment...")

    df = df.sort_values("SHOT_TIME")

    df["TIME_GAP_MINUTES"] = np.nan
    df["DOWNTIME_GAP_FLAG"] = False
    df["DOWNTIME_CT_FLAG"] = False
    df["DOWNTIME_EVENT"] = False

    if len(df) < 2:
        print("  Not enough data for downtime analysis")
        return df

    time_gaps = df["SHOT_TIME"].diff().dt.total_seconds() / 60.0
    typical_ct = df["DURATION"].median()
    ct_threshold = typical_ct * ct_multiplier

    downtime_gaps = time_gaps > gap_threshold
    downtime_ct_spikes = df["DURATION"] > ct_threshold

    df["TIME_GAP_MINUTES"] = time_gaps
    df["DOWNTIME_GAP_FLAG"] = downtime_gaps
    df["DOWNTIME_CT_FLAG"] = downtime_ct_spikes
    df["DOWNTIME_EVENT"] = downtime_gaps | downtime_ct_spikes

    calculate_downtime_statistics(df)
    print("  Downtime detection complete")
    return df


def calculate_downtime_statistics(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Print downtime statistics and return per-part downtime breakdown.

    Args:
        df: DataFrame with DOWNTIME_EVENT, DOWNTIME_GAP_FLAG,
            DOWNTIME_CT_FLAG, and TIME_GAP_MINUTES columns.

    Returns:
        Per-part downtime DataFrame, or None if PRODUCT_NAME is absent.
    """
    total_shots = len(df)
    downtime_events = int(df["DOWNTIME_EVENT"].sum())
    gap_downtimes = int(df["DOWNTIME_GAP_FLAG"].sum())
    ct_downtimes = int(df["DOWNTIME_CT_FLAG"].sum())

    print("\n  Downtime Statistics for Equipment:")
    print("   Total shots: %d" % total_shots)
    print(
        "   Downtime events: %d (%.1f%%)"
        % (downtime_events, (downtime_events / total_shots) * 100)
    )
    print("   Gap-based downtimes: %d" % gap_downtimes)
    print("   CT spike downtimes: %d" % ct_downtimes)

    part_downtime: Optional[pd.DataFrame] = None
    if "PRODUCT_NAME" in df.columns:
        part_downtime = (
            df.groupby("PRODUCT_NAME")
            .agg(
                {
                    "DOWNTIME_EVENT": "sum",
                    "DURATION": "count",
                    "TIME_GAP_MINUTES": ["mean", "max", "sum"],
                }
            )
            .round(2)
        )
        part_downtime.columns = [
            "Downtime_Events",
            "Total_Shots",
            "Avg_Gap_Min",
            "Max_Gap_Min",
            "Total_Idle_Min",
        ]
        part_downtime["Downtime_Rate"] = (
            part_downtime["Downtime_Events"] / part_downtime["Total_Shots"] * 100
        ).round(2)
        part_downtime = part_downtime.sort_values("Downtime_Rate", ascending=False)

        print("\n  Downtime by Part:")
        print(part_downtime.head(10))

    if gap_downtimes > 0:
        _print_equipment_downtime_summary(df)

    return part_downtime


def display_statistical_summary(df: pd.DataFrame) -> None:
    """Print an equipment-level downtime summary with gap statistics.

    This is a convenience wrapper kept for backward compatibility with
    callers that previously invoked ``_display_statistical_summary`` on the
    ParetoAnalysis class.

    Args:
        df: DataFrame with DOWNTIME columns already computed.
    """
    calculate_downtime_statistics(df)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _print_real_downtime_summary(df: pd.DataFrame) -> None:
    """Print total downtime seconds and event count."""
    total_downtime = df["DOWNTIME"].sum()
    downtime_events = int((df["DOWNTIME"] > 0).sum())
    total_shots = len(df)

    print(
        "   Total downtime: %.0f seconds (%.1f hours)"
        % (total_downtime, total_downtime / 3600)
    )
    print(
        "   Downtime events: %d shots (%.1f%%)"
        % (downtime_events, downtime_events / total_shots * 100)
    )


def _print_equipment_downtime_summary(df: pd.DataFrame) -> None:
    """Print average, max, and total idle time for the equipment."""
    positive_gaps = df[df["TIME_GAP_MINUTES"] > 0]
    avg_gap = positive_gaps["TIME_GAP_MINUTES"].mean()
    max_gap = df["TIME_GAP_MINUTES"].max()
    total_idle = df["TIME_GAP_MINUTES"].sum()

    print("\n  Equipment Downtime Summary:")
    print("   Average downtime gap: %.1f minutes" % avg_gap)
    print("   Maximum downtime gap: %.1f minutes" % max_gap)
    print("   Total idle time: %.1f minutes" % total_idle)
    print("   Typical duration: %.1f seconds" % df["DURATION"].median())
