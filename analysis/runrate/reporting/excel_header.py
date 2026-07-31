"""
Excel report header generation for RunRate analysis.

Handles creation of report headers, metadata, and data units sections.
"""

from typing import List, Optional, Tuple, Union

from .excel_styles import ExcelStyles, create_data_cell, create_header_cell


def create_report_header(
    worksheet,
    equipment_code: Optional[str] = None,
    date_range: Optional[Union[List[str], Tuple[str, str]]] = None,
):
    """
    Create report header section with equipment info and data units.

    Creates:
    - Tooling ID (A1-B1)
    - Date range (A2-B2)
    - Method (A3-B3)
    - Data units table (A5-B10)

    Args:
        worksheet: OpenPyXL worksheet object
        equipment_code: Equipment identifier
        date_range: [start_date, end_date] or (start_date, end_date)

    Example:
        >>> create_report_header(ws, "MX-7104", ["2025-01-01", "2025-12-31"])
    """
    ExcelStyles()

    # === LEFT COLUMN - Tooling Information ===
    # A1: Equipment Code
    create_header_cell(worksheet, "A1", "Tooling ID")
    create_data_cell(worksheet, "B1", equipment_code if equipment_code else "N/A")

    # A2: Date
    create_header_cell(worksheet, "A2", "Date")
    if (
        date_range is not None
        and isinstance(date_range, (list, tuple))
        and len(date_range) >= 2
    ):
        date_str = f"{date_range[0]} to {date_range[1]}"
    else:
        date_str = "N/A"
    create_data_cell(worksheet, "B2", date_str)

    # A3: Method
    create_header_cell(worksheet, "A3", "Method")
    create_data_cell(worksheet, "B3", "Every Shot")

    # === Data Units Section ===
    # A5: Data Units header
    create_header_cell(worksheet, "A5", "Data")
    create_header_cell(worksheet, "B5", "Unit")

    # Data units
    units_data = [
        ("Cycle Time", "Second"),
        ("Temperature", "°C (Celsius)"),
        ("Injection Time", "Second"),
        ("Packing Time", "Second"),
        ("Cooling Time", "Second"),
    ]

    for i, (data, unit) in enumerate(units_data, start=6):
        create_data_cell(worksheet, f"A{i}", data)
        create_data_cell(worksheet, f"B{i}", unit)


def create_production_metrics_section(
    worksheet,
    shot_data_start_row: int,
    shot_data_end_row: int,
):
    """
    Create production metrics section with formulas.

    Creates:
    - Mode CT calculation
    - Outside L1/L2 indicators
    - Total stops counter
    - Production time metrics
    - Efficiency calculations

    Args:
        worksheet: OpenPyXL worksheet object
        shot_data_start_row: Starting row of shot-level data
        shot_data_end_row: Ending row of shot-level data

    Example:
        >>> create_production_metrics_section(ws, 150, 1000)
    """
    styles = ExcelStyles()

    # E1: Mode CT Title
    create_header_cell(
        worksheet, "E1", "Mode CT", style_dict=styles.get_highlight_style("grey")
    )

    # E2: Mode CT Value - FORMULA (mode of ACTUAL_CT from main data table Column F)
    worksheet["E2"] = f"=MODE(F{shot_data_start_row}:F{shot_data_end_row})"
    worksheet["E2"].border = styles.THIN_BORDER
    worksheet["E2"].number_format = "0.00"  # 2 decimal places

    # Add warning note about Mode CT calculation
    worksheet["E3"] = "⚠️ GLOBAL Mode CT"
    worksheet["E3"].font = styles.BLACK_FONT
    worksheet["E3"].border = styles.THIN_BORDER

    worksheet["E4"] = "(Processing uses daily mode CT)"
    worksheet["E4"].font = styles.REGULAR_FONT
    worksheet["E4"].border = styles.THIN_BORDER

    # F1: Outside L1 (yellow background)
    create_header_cell(
        worksheet, "F1", "Outside L1", style_dict=styles.get_highlight_style("yellow")
    )

    # G1: Outside L2 (red background)
    create_header_cell(
        worksheet, "G1", "Outside L2", style_dict=styles.get_highlight_style("red")
    )

    # H1: Total Stops
    create_header_cell(
        worksheet, "H1", "Total Stops", style_dict=styles.get_highlight_style("grey")
    )

    # F2: Lower Limit
    create_header_cell(
        worksheet, "F2", "Lower Limit", style_dict=styles.get_highlight_style("grey")
    )

    # G2: Upper Limit
    create_header_cell(
        worksheet, "G2", "Upper Limit", style_dict=styles.get_highlight_style("grey")
    )

    # H2: Total Stops Value - FORMULA
    worksheet["H2"] = f'=COUNTIFS(H{shot_data_start_row}:H{shot_data_end_row},"1")'
    worksheet["H2"].border = styles.THIN_BORDER

    # F3: Lower limit value - FORMULA (95% of Mode CT in E2)
    worksheet["F3"] = "=E2*0.95"
    worksheet["F3"].border = styles.THIN_BORDER
    worksheet["F3"].number_format = "0.00"

    # G3: Upper limit value - FORMULA (105% of Mode CT in E2)
    worksheet["G3"] = "=E2*1.05"
    worksheet["G3"].border = styles.THIN_BORDER
    worksheet["G3"].number_format = "0.00"

    # F4: Production Time
    create_header_cell(
        worksheet,
        "F4",
        "Production Time",
        style_dict=styles.get_highlight_style("grey"),
    )

    # G4: Total Down Time
    create_header_cell(
        worksheet,
        "G4",
        "Total Down Time",
        style_dict=styles.get_highlight_style("grey"),
    )

    # F5: Production Time Value - Use PRODUCTION_TIME column (Column M)
    worksheet["F5"] = f"=MAX(M{shot_data_start_row}:M{shot_data_end_row})"
    worksheet["F5"].border = styles.THIN_BORDER
    worksheet["F5"].number_format = "0.00"

    # G5: Total Down Time Value - Use TOTAL_DOWN_TIME column (Column N)
    worksheet["G5"] = f"=MAX(N{shot_data_start_row}:N{shot_data_end_row})"
    worksheet["G5"].border = styles.THIN_BORDER
    worksheet["G5"].number_format = "0.00"

    # F6: Production Time % (of total)
    worksheet["F6"] = '=ROUND(F5/F8*100,2)&"%"'
    worksheet["F6"].border = styles.THIN_BORDER

    # G6: Downtime % (of total)
    worksheet["G6"] = '=ROUND(G5/F8*100,2)&"%"'
    worksheet["G6"].border = styles.THIN_BORDER

    # F7: Total Run Time Label
    create_header_cell(
        worksheet,
        "F7",
        "Total Run Time",
        style_dict=styles.get_highlight_style("grey"),
    )

    # F8: Total Run Time Value (Production + Downtime)
    worksheet["F8"] = "=F5+G5"
    worksheet["F8"].border = styles.THIN_BORDER
    worksheet["F8"].number_format = "0.00"

    # F9: Total Run Time in Hours
    worksheet["F9"] = '=ROUND(F8/60,2)&" Hours"'
    worksheet["F9"].border = styles.THIN_BORDER

    # === RIGHT SIDE METRICS (K, L, M, N columns) ===
    # Row 1: Shot Count Metrics
    create_header_cell(
        worksheet,
        "K1",
        "Total Shot Count",
        style_dict=styles.get_highlight_style("grey"),
    )

    create_header_cell(
        worksheet,
        "L1",
        "Normal Shot Count",
        style_dict=styles.get_highlight_style("grey"),
    )

    # K3: Efficiency Title
    create_header_cell(
        worksheet,
        "K3",
        "Efficiency %",
        style_dict=styles.get_highlight_style("grey"),
    )

    # Row 4: Stop Metrics
    create_header_cell(
        worksheet,
        "K4",
        "Stop Count (Events)",
        style_dict=styles.get_highlight_style("grey"),
    )

    create_header_cell(
        worksheet,
        "M4",
        "Individual Stops",
        style_dict=styles.get_highlight_style("grey"),
    )

    # Row 6: Reliability Section Header
    create_header_cell(
        worksheet,
        "K6",
        "Reliability Metrics",
        style_dict=styles.get_highlight_style("dark_blue"),
    )

    create_header_cell(
        worksheet,
        "L6",
        "Value",
        style_dict=styles.get_highlight_style("dark_blue"),
    )

    # Row 7-10: Reliability Metrics
    create_header_cell(
        worksheet,
        "K7",
        "MTTR (Avg)",
        style_dict=styles.get_highlight_style("grey"),
    )

    create_header_cell(
        worksheet,
        "K8",
        "MTBF (Avg)",
        style_dict=styles.get_highlight_style("grey"),
    )

    create_header_cell(
        worksheet,
        "K9",
        "Time to First DT (Avg)",
        style_dict=styles.get_highlight_style("grey"),
    )

    create_header_cell(
        worksheet,
        "K10",
        "Avg Cycle Time",
        style_dict=styles.get_highlight_style("grey"),
    )

    # Row 14-15: Time Bucket Analysis Section (Stop Events Only)
    create_header_cell(
        worksheet,
        "M14",
        "Time Bucket Analysis (Stop Events)",
        style_dict=styles.get_highlight_style("dark_blue"),
    )

    create_header_cell(
        worksheet,
        "M15",
        "Time Bucket (20min)",
        style_dict=styles.get_highlight_style("grey"),
    )

    create_header_cell(
        worksheet,
        "N15",
        "Stop Events Count",
        style_dict=styles.get_highlight_style("grey"),
    )


def create_section_separator(
    worksheet, row: int, message: str = "SUMMARY SECTION ENDS HERE"
):
    """
    Create a visual separator line in the worksheet.

    Args:
        worksheet: OpenPyXL worksheet object
        row: Row number for the separator
        message: Separator message

    Example:
        >>> create_section_separator(ws, 70, "DATA SECTION STARTS")
    """
    worksheet[f"A{row}"] = "=" * 100 + f" {message} " + "=" * 100
    worksheet[f"A{row}"].font = ExcelStyles.BLACK_FONT
