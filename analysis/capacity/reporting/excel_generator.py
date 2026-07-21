"""
Excel report generation for Capacity Analysis.

Generates multi-sheet workbooks with different OEE targets (50%-100%).

Author: Utku Gulbardak
Date: 2025-10-27
"""

from typing import Dict

import pandas as pd  # type: ignore[import-untyped]


def create_multi_oee_excel(
    all_daily_data: Dict[float, pd.DataFrame],
    output_file: str,
) -> str:
    """
    Create Excel workbook with multiple sheets for different OEE targets.

    Generates one sheet per OEE target (e.g., 50%_OEE, 60%_OEE, ..., 100%_OEE)
    with proper number formatting for financial/production reporting.

    Args:
        all_daily_data: Dict mapping OEE target (e.g., 0.60) to daily DataFrame
            Each DataFrame should contain daily aggregated metrics including:
            - DAY: Date column
            - ACTUAL_OUTPUT, OPTIMAL_OUTPUT, GAP, etc.
            - All OEE metrics and time calculations
        output_file: Output Excel file path

    Returns:
        str: Path to generated Excel file

    Example:
        >>> all_data = {
        ...     0.50: daily_df_50,
        ...     0.60: daily_df_60,
        ...     0.70: daily_df_70,
        ...     0.80: daily_df_80,
        ...     0.90: daily_df_90,
        ...     1.00: daily_df_100
        ... }
        >>> create_multi_oee_excel(all_data, "capacity_report.xlsx")
        'capacity_report.xlsx'
    """
    with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
        # Get the workbook object for formatting
        workbook = writer.book

        # Define number formats
        integer_format = workbook.add_format(
            {"num_format": "#,##0"}
        )  # No decimals, comma separator
        decimal_format = workbook.add_format(
            {"num_format": "#,##0.00"}
        )  # 2 decimals, comma separator

        # Process each OEE target
        for oee_target, daily_data in all_daily_data.items():
            sheet_name = f"{int(oee_target * 100)}%_OEE"
            daily_data.to_excel(writer, index=False, sheet_name=sheet_name)

            # Get the worksheet object for formatting
            worksheet = writer.sheets[sheet_name]

            # Columns that should be integers (no decimals): output, counts, shots
            integer_columns = [
                "ACTUAL_OUTPUT",
                "OPTIMAL_OUTPUT",
                "PERFORMANCE_LOSS",
                "AVAILABILITY_LOSS",
                "GAP",
                "TOTAL_SHOTS_ALL",
                "INVALID_999_SHOTS",
                "VALID_SHOTS",
                "CAVITY_COUNT",
                "QUALITY_PARTS",
                "OPTIMAL_OUTPUT_100_OEE",
                "OPTIMAL_OUTPUT_TARGET_OEE",
            ]

            # Columns that should have 2 decimals: times, rates, percentages
            decimal_columns = [
                "APPROVED_CT_SEC",
                "MODE_CT_SEC",
                "TOTAL_RUN_SEC",
                "PRODUCTION_TIME_SEC",
                "DOWNTIME_SEC",
                "AVAILABILITY",
                "PERFORMANCE",
                "QUALITY",
                "OEE_SCORE",
                "TARGET_OEE",
                "PLANNED_PRODUCTION_TIME_SEC",
                "RUN_TIME_SEC",
                "IDEAL_PRODUCTION_TIME_SEC",
                "EXTRA_TIME_SLOW_CYCLES_SEC",
            ]

            # Apply formatting to each column
            for col_num, col_name in enumerate(daily_data.columns):
                if col_name in integer_columns:
                    # Format entire column as integer with comma separator
                    worksheet.set_column(col_num, col_num, None, integer_format)
                elif col_name in decimal_columns:
                    # Format entire column as decimal with comma separator
                    worksheet.set_column(col_num, col_num, None, decimal_format)

            print(f"  ✅ Created sheet: {sheet_name} (with formatting)")

    print(f"Saved Excel workbook with {len(all_daily_data)} sheets → {output_file}")
    return output_file
