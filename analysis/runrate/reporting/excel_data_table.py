"""
Excel data table writer for RunRate analysis.

Handles writing shot-level data to Excel with proper column mapping and formatting.
"""

import pandas as pd

from .excel_styles import ExcelStyles


def write_data_table_headers(worksheet, start_row: int):
    """
    Write data table headers to the worksheet.

    Args:
        worksheet: OpenPyXL worksheet object
        start_row: Row number to start writing headers

    Returns:
        List of header names (for column mapping)
    """
    styles = ExcelStyles()

    headers = [
        "SUPPLIER NAME",
        "EQUIPMENT CODE",
        "SESSION ID",
        "SHOT TIME",
        "APPROVED CT",
        "ACTUAL CT",
        "TIME DIFF SEC",
        "STOP",
        "CUMULATIVE COUNT",
        "RUN DURATION",
        "TIME BUCKET",
        "PRODUCTION TIME",  # Session-level production time
        "TOTAL DOWN TIME",  # Session-level downtime
        "TOTAL RUN TIME",  # Session-level total time
        "TOTAL STOPS",  # Session-level stop events (grouped)
        "INDIVIDUAL STOPS",  # Individual shot stops
        # Removed EFFICIENCY, MTTR, MTBF (columns Q, R, S) - duplicates of Trends & Graphs sheet
    ]

    # Write headers
    for col, header in enumerate(headers, start=1):
        cell = worksheet.cell(row=start_row, column=col)
        cell.value = header
        cell.fill = styles.GREY_FILL
        cell.font = styles.BLACK_FONT
        cell.border = styles.THIN_BORDER

    # Set all column widths to 20
    for col in range(1, len(headers) + 1):
        col_letter = get_column_letter(col)
        worksheet.column_dimensions[col_letter].width = 20

    print(f"✅ Set column widths to 20 for {len(headers)} columns")

    return headers


def write_data_table_rows(
    worksheet,
    df_result: pd.DataFrame,
    start_row: int,
    max_rows: int = 375000,
):
    """
    Write shot-level data rows to the worksheet.

    Args:
        worksheet: OpenPyXL worksheet object
        df_result: DataFrame with shot data
        start_row: Row number to start writing data (after headers)
        max_rows: Maximum number of rows to write (Excel limit)

    Returns:
        Tuple of (rows_written, end_row)
    """
    # Limit data to max_rows
    df_write = df_result.head(max_rows)

    # Column mapping (0-indexed in DataFrame, 1-indexed in Excel)
    column_mapping = {
        "SUPPLIER_NAME": 1,
        "EQUIPMENT_CODE": 2,
        "SESSION_ID": 3,
        "LOCAL_SHOT_TIME": 4,
        "APPROVED_CT": 5,
        "ACTUAL_CT": 6,
        "SHOT_DIFF_SEC": 7,
        "STOP": 8,
        "CUMULATIVE_COUNT": 9,
        "RUN_DURATION": 10,
        "TIME_BUCKET": 11,
        "PRODUCTION_TIME": 12,
        "TOTAL_DOWN_TIME": 13,
        "TOTAL_RUN_TIME": 14,
        "TOTAL_STOPS": 15,
        "INDIVIDUAL_STOPS": 16,
        # Removed EFFICIENCY (17), MTTR (18), MTBF (19)
    }

    styles = ExcelStyles()

    # Write data rows
    for row_idx, (_, row) in enumerate(df_write.iterrows(), start=start_row):
        for col_name, col_num in column_mapping.items():
            if col_name in row.index:
                cell = worksheet.cell(row=row_idx, column=col_num)
                cell.value = row[col_name]
                cell.border = styles.THIN_BORDER

                # Format specific columns
                if col_name in ["APPROVED_CT", "ACTUAL_CT", "SHOT_DIFF_SEC"]:
                    cell.number_format = "0.00"
                elif col_name in [
                    "PRODUCTION_TIME",
                    "TOTAL_DOWN_TIME",
                    "TOTAL_RUN_TIME",
                ]:
                    cell.number_format = "0.00"
                elif col_name in ["EFFICIENCY", "MTTR", "MTBF"]:
                    cell.number_format = "0.00"
                elif col_name == "LOCAL_SHOT_TIME":
                    cell.number_format = "yyyy-mm-dd hh:mm:ss"

    rows_written = len(df_write)
    end_row = start_row + rows_written - 1

    print(f"📝 Wrote {rows_written:,} rows of shot-level data")

    return rows_written, end_row


def get_column_letter(col_num: int) -> str:
    """
    Convert column number to Excel column letter.

    Args:
        col_num: Column number (1-indexed)

    Returns:
        Column letter (e.g., "A", "B", "AA", "AB")

    Example:
        >>> get_column_letter(1)
        'A'
        >>> get_column_letter(27)
        'AA'
    """
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(col_num % 26 + 65) + result
        col_num //= 26
    return result


def get_data_range_reference(start_row: int, end_row: int, column: int) -> str:
    """
    Create Excel range reference string.

    Args:
        start_row: Starting row number
        end_row: Ending row number
        column: Column number (1-indexed)

    Returns:
        Range reference (e.g., "A10:A1000")

    Example:
        >>> get_data_range_reference(10, 1000, 1)
        'A10:A1000'
    """
    col_letter = get_column_letter(column)
    return f"{col_letter}{start_row}:{col_letter}{end_row}"
