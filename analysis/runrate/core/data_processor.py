"""
Data preprocessing functions for RunRate analysis.

Handles data cleaning, session creation, and test shot filtering.
"""

import pandas as pd

from analysis.shared.constants import SessionDetection


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Preprocess production data and create sessions.

    Sessions are split at:
    1. Midnight (date change)
    2. 8-hour breaks or longer

    This prevents long breaks from being counted as production or downtime.
    Removes duplicates and calculates time differences between consecutive shots.

    Args:
        df: Raw production data with columns:
            - EQUIPMENT_CODE
            - LOCAL_SHOT_TIME
            - SUPPLIER_NAME
            - ACTUAL_CT
            - APPROVED_CT

    Returns:
        pd.DataFrame: Preprocessed data with added columns:
            - SHOT_DIFF_SEC: Time difference to previous shot (seconds)
            - SHOT_DATE: Date of the shot
            - DATE_CHANGE: Boolean indicating midnight cutoff
            - LONG_BREAK: Boolean indicating 8+ hour break
            - SESSION_BREAK: Boolean indicating any session break
            - SESSION_ID: Session identifier (can have multiple per day)

    Example:
        >>> df_raw = load_data("SUPPLIER_A")
        >>> df_processed = preprocess_data(df_raw)
        >>> print(df_processed.columns)
        ['EQUIPMENT_CODE', 'LOCAL_SHOT_TIME', ..., 'SESSION_ID']
    """
    df = df.copy()
    df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])
    df = df.sort_values(["EQUIPMENT_CODE", "LOCAL_SHOT_TIME"])

    # Remove duplicate records based on equipment, time, and supplier
    df = df.drop_duplicates(
        subset=["EQUIPMENT_CODE", "LOCAL_SHOT_TIME", "SUPPLIER_NAME"], keep="first"
    )

    # Calculate time difference between consecutive shots (in seconds)
    df["SHOT_DIFF_SEC"] = (
        df.groupby("EQUIPMENT_CODE")["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
    )

    # First, create daily splits (midnight cutoff)
    df["SHOT_DATE"] = df["LOCAL_SHOT_TIME"].dt.date
    df["DATE_CHANGE"] = (
        df.groupby("EQUIPMENT_CODE")["SHOT_DATE"]
        .transform(lambda x: x != x.shift(1))
        .fillna(True)  # First shot of each equipment is a new session
        .astype(int)
    )

    # Second, create 8-hour break splits within the same day
    df["LONG_BREAK"] = (
        (df["SHOT_DIFF_SEC"] > SessionDetection.SESSION_GAP_SECONDS)
        & df["SHOT_DIFF_SEC"].notna()
    ).astype(int)

    # Combine both types of session breaks
    df["SESSION_BREAK"] = (df["DATE_CHANGE"] | df["LONG_BREAK"]).astype(int)
    df["SESSION_ID"] = df.groupby("EQUIPMENT_CODE")["SESSION_BREAK"].cumsum()

    return df


def filter_test_shots_within_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove individual test shots within sessions that create large artificial downtimes.

    Identifies and removes shots that are:
    1. Followed by a large time gap (> 2 hours) within the same session
    2. Have cycle times very different from approved CT (< 70% or > 150% of approved)
    3. Are isolated shots before main production starts (first 5 shots)

    Args:
        df: Preprocessed DataFrame with SESSION_ID

    Returns:
        pd.DataFrame: Filtered data with test shots removed and SESSION_ID recalculated

    Notes:
        - Single-shot sessions are skipped
        - SESSION_ID is recalculated after removal to maintain sequential numbering
        - SHOT_DIFF_SEC is recalculated after removal
    """
    print("🧹 Filtering individual test shots within sessions...")

    df = df.copy()
    shots_to_remove = []

    for (equipment_code, session_id), session_df in df.groupby(
        ["EQUIPMENT_CODE", "SESSION_ID"]
    ):
        if len(session_df) <= 1:
            continue  # Skip single-shot sessions

        session_df = session_df.sort_values("LOCAL_SHOT_TIME").reset_index()

        for i in range(len(session_df) - 1):  # Don't check last shot
            current_shot = session_df.iloc[i]
            next_shot = session_df.iloc[i + 1]

            # Calculate time gap to next shot in the same session
            time_gap_hours = (
                next_shot["LOCAL_SHOT_TIME"] - current_shot["LOCAL_SHOT_TIME"]
            ).total_seconds() / 3600

            # Calculate cycle time deviation from approved CT
            approved_ct = current_shot["APPROVED_CT"]
            actual_ct = current_shot["ACTUAL_CT"]

            if approved_ct > 0:
                ct_ratio = actual_ct / approved_ct
            else:
                ct_ratio = 1.0  # Fallback if no approved CT

            # Identify test shots:
            # 1. Large gap to next shot (> 2 hours) AND
            # 2. Cycle time different from approved (< 70% or > 150%) AND
            # 3. This is early in the session (first 5 shots)
            is_test_shot = (
                time_gap_hours > 2.0  # Large gap to next shot
                and (
                    ct_ratio < 0.7 or ct_ratio > 1.5
                )  # CT differs significantly from approved
                and i < 5  # Early in session (first 5 shots)
            )

            if is_test_shot:
                shots_to_remove.append(current_shot["index"])
                print(
                    f"   🚫 Removing test shot: Equipment {equipment_code}, Session {session_id}"
                )
                print(f"      Shot time: {current_shot['LOCAL_SHOT_TIME']}")
                print(
                    f"      Actual CT: {actual_ct:.1f}s vs Approved CT: {approved_ct:.1f}s (ratio: {ct_ratio:.2f})"
                )
                print(f"      Gap to next shot: {time_gap_hours:.1f} hours")

    # Remove identified test shots
    if shots_to_remove:
        print(f"   ✅ Removing {len(shots_to_remove)} test shots")
        df_filtered = df.drop(shots_to_remove).reset_index(drop=True)

        # Recalculate SESSION_ID to maintain sequential numbering after removal
        df_filtered = df_filtered.sort_values(["EQUIPMENT_CODE", "LOCAL_SHOT_TIME"])
        df_filtered["SHOT_DATE"] = df_filtered["LOCAL_SHOT_TIME"].dt.date
        df_filtered["DATE_CHANGE"] = (
            df_filtered.groupby("EQUIPMENT_CODE")["SHOT_DATE"]
            .transform(lambda x: x != x.shift(1))
            .astype(int)
        )
        df_filtered["SESSION_ID"] = df_filtered.groupby("EQUIPMENT_CODE")[
            "DATE_CHANGE"
        ].cumsum()

        # Recalculate shot differences after removing test shots
        df_filtered["SHOT_DIFF_SEC"] = (
            df_filtered.groupby("EQUIPMENT_CODE")["LOCAL_SHOT_TIME"]
            .diff()
            .dt.total_seconds()
        )

        print(
            f"   📊 Filtered data: {len(df_filtered):,} shots (removed {len(df) - len(df_filtered):,} test shots)"
        )
        return df_filtered
    else:
        print("   ✅ No test shots found to remove")
        return df


def calculate_session_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate aggregated statistics per session.

    Args:
        df: Processed DataFrame with session-level data

    Returns:
        pd.DataFrame: Session-level statistics with one row per session
    """
    stats = (
        df.groupby(["EQUIPMENT_CODE", "SESSION_ID"])
        .agg(
            {
                "LOCAL_SHOT_TIME": ["min", "max", "count"],
                "STOP": "sum",
                "SHOT_DIFF_SEC": "sum",
                "MODE_CT": "first",
            }
        )
        .reset_index()
    )

    # Flatten column names
    stats.columns = [
        "EQUIPMENT_CODE",
        "SESSION_ID",
        "SESSION_START",
        "SESSION_END",
        "TOTAL_SHOTS",
        "TOTAL_STOPS",
        "TOTAL_TIME_SEC",
        "MODE_CT",
    ]

    # Calculate session duration and efficiency
    stats["SESSION_DURATION_MIN"] = stats["TOTAL_TIME_SEC"] / 60
    stats["EFFICIENCY_PCT"] = (
        (stats["TOTAL_SHOTS"] - stats["TOTAL_STOPS"]) / stats["TOTAL_SHOTS"] * 100
    )

    return stats
