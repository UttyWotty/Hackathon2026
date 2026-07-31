"""
Data Processing for Capacity Analysis.

Handles shot-level data processing, session splitting, and cavity calculations.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import pandas as pd  # type: ignore[import-untyped]

from analysis.shared.constants import SessionDetection

from ..models.config import EQUIPMENT_CAVITY_MAPPING


def _print_session_summary(data: pd.DataFrame) -> None:
    """Print overall session summary information."""
    session_count = data["SESSION_ID"].nunique()
    date_range = f"{data['LOCAL_SHOT_TIME'].min().date()} to {data['LOCAL_SHOT_TIME'].max().date()}"
    print(f"📊 Created {session_count} sessions across date range: {date_range}")


def _print_equipment_session_details(eq_data: pd.DataFrame, equipment: str) -> None:
    """Print detailed session breakdown for a single equipment."""
    eq_sessions = eq_data["SESSION_ID"].nunique()
    eq_days = eq_data["SHOT_DATE"].nunique()
    print(f"   {equipment}: {eq_sessions} sessions across {eq_days} days")

    print(f"   🔍 Session breakdown for {equipment}:")
    for session_id in sorted(eq_data["SESSION_ID"].unique())[:5]:
        session_data = eq_data[eq_data["SESSION_ID"] == session_id]
        start_time = session_data["LOCAL_SHOT_TIME"].min()
        end_time = session_data["LOCAL_SHOT_TIME"].max()
        shot_count = len(session_data)
        duration_hours = (end_time - start_time).total_seconds() / 3600
        print(
            f"     Session {session_id}: {start_time.strftime('%Y-%m-%d %H:%M')} → {end_time.strftime('%H:%M')} ({duration_hours:.1f}h, {shot_count} shots)"
        )


def _print_session_summary_table(eq_data: pd.DataFrame) -> None:
    """Print session summary table with break information."""
    session_summary = (
        eq_data.groupby("SESSION_ID")
        .agg(
            {
                "LOCAL_SHOT_TIME": ["min", "max", "count"],
                "SHOT_DATE": "first",
                "LONG_BREAK": "max",
                "DATE_CHANGE": "max",
            }
        )
        .head(5)
    )

    for session_id, row in session_summary.iterrows():
        start_time = row[("LOCAL_SHOT_TIME", "min")]
        end_time = row[("LOCAL_SHOT_TIME", "max")]
        shot_count = row[("LOCAL_SHOT_TIME", "count")]
        date = row[("SHOT_DATE", "first")]
        had_long_break = row[("LONG_BREAK", "max")]
        had_date_change = row[("DATE_CHANGE", "max")]

        break_type = []
        if had_date_change:
            break_type.append("midnight")
        if had_long_break:
            break_type.append("8h+")
        break_info = f" ({'+'.join(break_type)} break)" if break_type else ""

        duration_hours = (end_time - start_time).total_seconds() / 3600
        print(
            f"     Session {session_id}: {date} {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} "
            f"({duration_hours:.1f}h, {shot_count} shots){break_info}"
        )


def _print_session_debug_info(data: pd.DataFrame) -> None:
    """Print debug information about session splits."""
    if data.empty:
        return

    _print_session_summary(data)

    # Show detailed session breakdown per equipment
    for equipment in data["EQUIPMENT_CODE"].unique()[:3]:
        eq_data = data[data["EQUIPMENT_CODE"] == equipment]
        _print_equipment_session_details(eq_data, equipment)
        _print_session_summary_table(eq_data)

    print(
        f"🔧 Session split triggers: {data['DATE_CHANGE'].sum()} midnight breaks, {data['LONG_BREAK'].sum()} 8h+ breaks"
    )


def add_shot_diffs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add shot-to-shot time differences in seconds per equipment and create sessions.

    Sessions are split at:
    1. Midnight (date change)
    2. 8-hour breaks or longer

    Args:
        df: DataFrame with columns: EQUIPMENT_CODE, LOCAL_SHOT_TIME

    Returns:
        pd.DataFrame: Input data with additional columns:
            - SHOT_DIFF_SEC: Time difference between consecutive shots (seconds)
            - SHOT_DATE: Date of the shot
            - DATE_CHANGE: Boolean indicating midnight cutoff
            - LONG_BREAK: Boolean indicating 8+ hour break
            - SESSION_BREAK: Boolean indicating any session break
            - SESSION_ID: Unique session identifier per equipment

    Example:
        >>> df = pd.DataFrame({
        ...     'EQUIPMENT_CODE': ['A', 'A', 'A'],
        ...     'LOCAL_SHOT_TIME': pd.to_datetime([
        ...         '2025-01-01 08:00:00',
        ...         '2025-01-01 08:01:00',
        ...         '2025-01-02 08:00:00'  # Midnight break
        ...     ])
        ... })
        >>> result = add_shot_diffs(df)
        >>> print(result['SESSION_ID'].unique())
        [1, 2]  # Two sessions due to midnight break
    """
    data = df.copy()
    data = data.sort_values(["EQUIPMENT_CODE", "LOCAL_SHOT_TIME"])
    data["SHOT_DIFF_SEC"] = (
        data.groupby("EQUIPMENT_CODE")["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
    )

    # Create sessions that split at midnight OR 8-hour breaks
    data["SHOT_DATE"] = data["LOCAL_SHOT_TIME"].dt.date
    data["DATE_CHANGE"] = (
        data.groupby("EQUIPMENT_CODE")["SHOT_DATE"]
        .transform(lambda x: x != x.shift(1))
        .fillna(True)
        .astype(int)
    )

    data["LONG_BREAK"] = (
        (data["SHOT_DIFF_SEC"] > SessionDetection.SESSION_GAP_SECONDS)
        & data["SHOT_DIFF_SEC"].notna()
    ).astype(int)

    data["SESSION_BREAK"] = (data["DATE_CHANGE"] | data["LONG_BREAK"]).astype(int)
    data["SESSION_ID"] = data.groupby("EQUIPMENT_CODE")["SESSION_BREAK"].cumsum()

    # Print debug information
    _print_session_debug_info(data)

    return data


def get_cavity_count(equipment_code: str, data: pd.DataFrame = None) -> int:
    """
    Get the cavity count for an equipment code.

    Multi-cavity molds produce multiple parts per shot.

    Logic:
    1. First checks hardcoded mapping (for equipment with incorrect system data)
    2. If not in mapping and data provided, calculates from VOLUME column
    3. Otherwise defaults to 1

    Args:
        equipment_code: Equipment code to look up
        data: Optional DataFrame with VOLUME column to calculate cavity count

    Returns:
        int: Number of parts produced per shot (default: 1 if not calculable)

    Example:
        >>> get_cavity_count("MX-7102")
        4  # Hardcoded value (system has wrong data)
        >>> get_cavity_count("OTHER-CODE", df)
        2  # Calculated from VOLUME column (mode)
        >>> get_cavity_count("UNKNOWN-CODE")
        1  # Default when no data available
    """
    # First check hardcoded mapping (these have incorrect system data)
    if equipment_code in EQUIPMENT_CAVITY_MAPPING:
        return EQUIPMENT_CAVITY_MAPPING[equipment_code]

    # If data provided, calculate from VOLUME column
    if data is not None and not data.empty and "VOLUME" in data.columns:
        # Filter for this equipment
        equipment_data = data[data["EQUIPMENT_CODE"] == equipment_code]

        if not equipment_data.empty:
            # Get mode of VOLUME (most common parts per shot)
            volume_values = equipment_data["VOLUME"].dropna()
            volume_values = volume_values[volume_values > 0]  # Only positive values

            if not volume_values.empty:
                # Calculate mode (most frequent value)
                cavity_from_volume = (
                    int(volume_values.mode().iloc[0])
                    if len(volume_values.mode()) > 0
                    else 1
                )
                print(
                    f"   📊 Equipment {equipment_code}: Calculated cavity count = {cavity_from_volume} (from VOLUME)"
                )
                return cavity_from_volume

    # Default to 1 if not in mapping and can't calculate from data
    print(f"   ⚠️ Equipment {equipment_code}: Using default cavity count = 1")
    return 1


def filter_sessions_by_shot_count(
    df: pd.DataFrame, min_shots: int = 10
) -> pd.DataFrame:
    """
    Filter out sessions with fewer than minimum shot count.

    This improves data quality by removing sessions that are too short
    to provide meaningful analysis.

    Args:
        df: DataFrame with SESSION_ID column
        min_shots: Minimum number of shots required per session

    Returns:
        pd.DataFrame: Filtered data containing only valid sessions

    Example:
        >>> df = add_shot_diffs(raw_data)
        >>> valid_sessions = filter_sessions_by_shot_count(df, min_shots=50)
        >>> print(f"Kept {len(valid_sessions)} of {len(df)} shots")
    """
    if df.empty:
        return df

    # Count shots per session
    session_counts = df.groupby("SESSION_ID").size()

    # Find sessions with enough shots
    valid_sessions = session_counts[session_counts >= min_shots].index

    # Filter data
    filtered_df = df[df["SESSION_ID"].isin(valid_sessions)].copy()

    removed_sessions = len(session_counts) - len(valid_sessions)
    if removed_sessions > 0:
        print(f"⚠️  Filtered out {removed_sessions} sessions with < {min_shots} shots")
        print(
            f"✅ Kept {len(valid_sessions)} valid sessions ({len(filtered_df)} shots)"
        )

    return filtered_df
