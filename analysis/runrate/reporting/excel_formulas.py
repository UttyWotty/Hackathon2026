"""
Excel formula generation for RunRate analysis.

Generates Excel formulas for dynamic calculations in reports.
"""

from typing import Optional

import pandas as pd

from .excel_styles import ExcelStyles


def update_summary_formulas(
    worksheet,
    main_data_start: int,
    main_data_end: int,
    df_result: pd.DataFrame,
):
    """
    Update summary section formulas with actual data ranges.

    Args:
        worksheet: OpenPyXL worksheet object
        main_data_start: Starting row of main data
        main_data_end: Ending row of main data
        df_result: DataFrame with session data (for aggregations)
    """
    # Calculate session-level averages
    session_mode_cts = (
        df_result.groupby(["EQUIPMENT_CODE", "SESSION_ID"])["MODE_CT"].first().dropna()
    )
    avg_mode_ct = session_mode_cts.mean() if not session_mode_cts.empty else 0.0

    # E2: Average Mode CT across all sessions
    worksheet["E2"] = avg_mode_ct

    # H2: Total Stop Events (session-level, sum of unique TOTAL_STOPS per session)
    # Column O is TOTAL_STOPS (session-level)
    worksheet["H2"] = (
        f"=SUMPRODUCT((1/COUNTIFS(C${main_data_start}:C${main_data_end},"
        f"C${main_data_start}:C${main_data_end}))*O{main_data_start}:O{main_data_end})"
    )

    # F5: Production Time (sum of unique session production times)
    # Column L is PRODUCTION_TIME (session-level)
    worksheet["F5"] = (
        f"=SUMPRODUCT((1/COUNTIFS(C${main_data_start}:C${main_data_end},"
        f"C${main_data_start}:C${main_data_end}))*L{main_data_start}:L{main_data_end})"
    )

    # G5: Total Down Time (sum of unique session downtimes)
    # Column M is TOTAL_DOWN_TIME (session-level)
    worksheet["G5"] = (
        f"=SUMPRODUCT((1/COUNTIFS(C${main_data_start}:C${main_data_end},"
        f"C${main_data_start}:C${main_data_end}))*M{main_data_start}:M{main_data_end})"
    )

    # K2: Total Shot Count
    worksheet["K2"] = f"=COUNT(H${main_data_start}:H${main_data_end})"

    # L2: Normal Shot Count = Total shots - Individual stops
    worksheet["L2"] = "=K2-M5"

    # L3: Efficiency % = (Normal shots / Total shots) * 100
    worksheet["L3"] = '=ROUND(L2/K2*100,2)&"%"'

    # L4: Stop Events Count (session-level)
    # Column O is TOTAL_STOPS (session-level stop events)
    worksheet["L4"] = (
        f"=SUMPRODUCT((1/COUNTIFS(C${main_data_start}:C${main_data_end},"
        f"C${main_data_start}:C${main_data_end}))*O{main_data_start}:O{main_data_end})"
    )

    # M5: Individual Stops Count
    # Column P is INDIVIDUAL_STOPS (individual shot stops)
    worksheet["M5"] = (
        f"=SUMPRODUCT((1/COUNTIFS(C${main_data_start}:C${main_data_end},"
        f"C${main_data_start}:C${main_data_end}))*P{main_data_start}:P{main_data_end})"
    )

    # Calculate session-level metrics averages
    # First, get shot count per session to filter out small sessions
    shots_per_session = (
        df_result.groupby(["EQUIPMENT_CODE", "SESSION_ID"])
        .size()
        .reset_index(name="SHOT_COUNT")
    )

    session_metrics = (
        df_result.groupby(["EQUIPMENT_CODE", "SESSION_ID"])
        .agg({"MTTR": "first", "MTBF": "first", "TIME_TO_FIRST_DT": "first"})
        .reset_index()
    )

    # Merge shot counts
    session_metrics = session_metrics.merge(
        shots_per_session, on=["EQUIPMENT_CODE", "SESSION_ID"]
    )

    # Filter out small sessions (< 3 shots) - likely cross-day artifacts
    # These single-shot sessions skew MTTR/MTBF averages
    main_sessions = session_metrics[session_metrics["SHOT_COUNT"] >= 3]

    # If all sessions filtered out, use all sessions (edge case)
    if main_sessions.empty:
        main_sessions = session_metrics

    # Calculate averages from main sessions only
    avg_mttr = main_sessions["MTTR"].mean() if not main_sessions.empty else 0.0
    avg_mtbf = main_sessions["MTBF"].mean() if not main_sessions.empty else 0.0
    avg_time_to_first_dt = (
        main_sessions["TIME_TO_FIRST_DT"].mean() if not main_sessions.empty else 0.0
    )

    # L7: MTTR (session-level average)
    worksheet["L7"] = round(avg_mttr, 2)

    # L8: MTBF (session-level average)
    worksheet["L8"] = round(avg_mtbf, 2)

    # L9: Time to First Downtime (session-level average)
    worksheet["L9"] = round(avg_time_to_first_dt, 2)

    # L10: Average Cycle Time
    worksheet["L10"] = f"=ROUND(AVERAGE(F${main_data_start}:F${main_data_end}),2)"


def update_time_bucket_formulas(
    worksheet,
    start_row: int,
    df_result: pd.DataFrame,
):
    """
    Update time bucket analysis with counts from data.

    Args:
        worksheet: OpenPyXL worksheet object
        start_row: Starting row for time bucket data (typically row 16)
        df_result: DataFrame with shot data
    """
    # Calculate time bucket counts
    time_bucket_counts = {}
    no_bucket_count = 0

    # Count STOP EVENTS (not individual stops)
    # Stop events are identified by having a RUN_DURATION value (not empty string "")
    # Back-to-back stops have RUN_DURATION = "" and should NOT be counted
    if not df_result.empty:
        # Get only stop EVENTS (first stop in a sequence with RUN_DURATION)
        # RUN_DURATION is a value (numeric or 0) for stop events, "" for back-to-back stops
        stop_events = df_result[
            (df_result["STOP"] == 1)
            & (df_result["RUN_DURATION"] != "")  # Not empty string (back-to-back stop)
            & (df_result["RUN_DURATION"].notna())  # Not NaN
        ].copy()

        if not stop_events.empty:
            # For stops WITH time buckets (have run duration > 0)
            stops_with_bucket = stop_events[stop_events["TIME_BUCKET"].notna()]
            if not stops_with_bucket.empty:
                time_bucket_counts = (
                    stops_with_bucket["TIME_BUCKET"].value_counts().to_dict()
                )

            # For stops WITHOUT time buckets (RUN_DURATION = 0, first shot was a stop)
            stops_no_bucket = stop_events[stop_events["TIME_BUCKET"].isna()]
            no_bucket_count = len(stops_no_bucket)

    # Write bucket counts with labels and proper styling
    styles = ExcelStyles()
    row_num = start_row
    grand_total = 0

    # Get all unique bucket numbers from the data (sorted)
    all_buckets = sorted(time_bucket_counts.keys()) if time_bucket_counts else []

    # Write each bucket with its count
    for bucket in all_buckets:
        count = time_bucket_counts[bucket]

        # Bucket number in M column
        m_cell = worksheet[f"M{row_num}"]
        m_cell.value = bucket
        m_cell.border = styles.THIN_BORDER

        # Count in N column
        n_cell = worksheet[f"N{row_num}"]
        n_cell.value = count
        n_cell.border = styles.THIN_BORDER

        grand_total += count
        row_num += 1

    # Add "No Bucket" row for stops without time buckets
    if no_bucket_count > 0:
        m_no_bucket = worksheet[f"M{row_num}"]
        m_no_bucket.value = "No Bucket"
        m_no_bucket.border = styles.THIN_BORDER

        n_no_bucket = worksheet[f"N{row_num}"]
        n_no_bucket.value = no_bucket_count
        n_no_bucket.border = styles.THIN_BORDER

        grand_total += no_bucket_count
        row_num += 1

    # Write grand total row with styling
    m_total_cell = worksheet[f"M{row_num}"]
    m_total_cell.value = "Grand Total"
    m_total_cell.fill = styles.GREY_FILL
    m_total_cell.font = styles.BLACK_FONT
    m_total_cell.border = styles.THIN_BORDER

    n_total_cell = worksheet[f"N{row_num}"]
    n_total_cell.value = grand_total
    n_total_cell.fill = styles.GREY_FILL
    n_total_cell.font = styles.BLACK_FONT
    n_total_cell.border = styles.THIN_BORDER


def create_mode_ct_formula(start_row: int, end_row: int, column: str = "F") -> str:
    """
    Create MODE formula for cycle time.

    Args:
        start_row: Starting row of data
        end_row: Ending row of data
        column: Column letter (default "F" for ACTUAL_CT)

    Returns:
        Excel MODE formula string

    Example:
        >>> create_mode_ct_formula(100, 1000)
        '=MODE(F100:F1000)'
    """
    return f"=MODE({column}{start_row}:{column}{end_row})"


def create_countifs_formula(
    range_ref: str, criteria: str, count_column: Optional[str] = None
) -> str:
    """
    Create COUNTIFS formula.

    Args:
        range_ref: Range reference (e.g., "H100:H1000")
        criteria: Criteria string (e.g., "1" or ">0")
        count_column: Optional column to count (for COUNTIFS vs SUMIFS)

    Returns:
        Excel COUNTIFS formula string

    Example:
        >>> create_countifs_formula("H100:H1000", "1")
        '=COUNTIFS(H100:H1000,"1")'
    """
    return f'=COUNTIFS({range_ref},"{criteria}")'


def create_sumproduct_unique_formula(
    session_column: str, value_column: str, start_row: int, end_row: int
) -> str:
    """
    Create SUMPRODUCT formula for summing unique session values.

    This formula sums values while avoiding duplication from repeated
    session rows. Uses 1/COUNTIFS to weight each unique session once.

    Args:
        session_column: Column letter for session ID (e.g., "C")
        value_column: Column letter for values to sum (e.g., "L")
        start_row: Starting row of data
        end_row: Ending row of data

    Returns:
        Excel SUMPRODUCT formula string

    Example:
        >>> create_sumproduct_unique_formula("C", "L", 100, 1000)
        '=SUMPRODUCT((1/COUNTIFS(C$100:C$1000,C$100:C$1000))*L100:L1000)'
    """
    session_range = f"{session_column}${start_row}:{session_column}${end_row}"
    value_range = f"{value_column}{start_row}:{value_column}{end_row}"

    return f"=SUMPRODUCT((1/COUNTIFS({session_range},{session_range}))*{value_range})"


def create_efficiency_formula(normal_shots_ref: str, total_shots_ref: str) -> str:
    """
    Create efficiency percentage formula.

    Args:
        normal_shots_ref: Cell reference for normal shots (e.g., "L2")
        total_shots_ref: Cell reference for total shots (e.g., "K2")

    Returns:
        Excel formula string with percentage formatting

    Example:
        >>> create_efficiency_formula("L2", "K2")
        '=ROUND(L2/K2*100,2)&"%"'
    """
    return f'=ROUND({normal_shots_ref}/{total_shots_ref}*100,2)&"%"'
