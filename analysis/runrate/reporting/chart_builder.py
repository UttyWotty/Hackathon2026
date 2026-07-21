"""
Chart building for Excel reports.

Creates daily trend charts and visualizations for RunRate analysis.
This module uses modular components for aggregation and chart generation.
"""

import pandas as pd
from openpyxl.styles import Font, PatternFill

from .daily_aggregation import aggregate_sessions_to_daily, create_daily_data_table
from .excel_charts import create_all_trend_charts


def create_daily_trends_sheet(graphs_ws, df_result: pd.DataFrame, main_ws=None):
    """
    Create daily aggregated trends on a dedicated graphs sheet.

        This function creates comprehensive daily trend analysis including:
        - Daily stop counts and efficiency metrics
        - MTTR/MTBF trends over time
        - Production vs downtime charts
        - Session-level aggregations

        Args:
            graphs_ws: Worksheet object for graphs
            df_result: Processed session DataFrame with metrics
            main_ws: Optional main worksheet reference

    Returns:
        None (modifies workbook in place)

    Notes:
        - Aggregates session-level metrics to avoid duplication
        - Creates both data tables and charts
        - Uses openpyxl for Excel generation

    Architecture:
        Uses modular components for maintainability:
        - daily_aggregation: Session-to-daily aggregation and deduplication
        - excel_charts: Chart creation with OpenPyXL

    Refactored Implementation:
        This function now uses modular components extracted from the
        original implementation. Benefits include:
        ✓ Testable aggregation logic
        ✓ Reusable chart creation
        ✓ Clear separation of concerns
        ✓ Easier to maintain and extend
    """
    try:
        # Step 1: Aggregate sessions to daily summaries
        daily_summary = aggregate_sessions_to_daily(df_result)

        if daily_summary.empty:
            print("   ⚠️ No daily data created")
            return

        # Step 2: Create header section
        _create_graphs_sheet_header(graphs_ws, daily_summary)

        # Step 3: Create daily data table
        data_start_row, data_end_row = create_daily_data_table(
            graphs_ws, daily_summary, start_row=7
        )

        # Step 4: Create all trend charts
        create_all_trend_charts(
            graphs_ws,
            main_ws,
            data_start_row,
            data_end_row,
        )

        print("   ✅ Daily trends sheet completed successfully")

    except Exception as e:
        print(f"   ❌ Error creating daily trends sheet: {e}")
        # Don't raise - allow Excel generation to continue without charts
        import traceback

        traceback.print_exc()


def _create_graphs_sheet_header(graphs_ws, daily_summary: pd.DataFrame):
    """
    Create header section for graphs worksheet.

    Args:
        graphs_ws: Worksheet object
        daily_summary: Daily aggregated data for metadata
    """
    # Define styles
    light_blue_fill = PatternFill(
        start_color="E1F5FE", end_color="E1F5FE", fill_type="solid"
    )

    # Title
    graphs_ws["A1"] = "📊 DAILY PRODUCTION TRENDS ANALYSIS"
    graphs_ws["A1"].font = Font(bold=True, size=16, color="1F4E79")
    graphs_ws["A1"].fill = light_blue_fill

    # Equipment info
    equipment_list = daily_summary["EQUIPMENT_CODE"].unique()
    graphs_ws["A3"] = (
        f"Equipment: {', '.join(equipment_list[:3])}{'...' if len(equipment_list) > 3 else ''}"
    )
    graphs_ws["A3"].font = Font(bold=True)

    # Date range
    date_range = (
        f"{daily_summary['SHOT_DATE'].min()} to {daily_summary['SHOT_DATE'].max()}"
    )
    graphs_ws["A4"] = f"Date Range: {date_range}"
    graphs_ws["A4"].font = Font(bold=True)
