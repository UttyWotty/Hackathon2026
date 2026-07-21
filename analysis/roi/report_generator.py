"""
ROI Report Generator
====================

Generates professional Excel reports with formatting, formulas, and summaries.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional

import pandas as pd


class ROIReportGenerator:
    """
    Generates professional Excel reports for ROI analysis.

    Features:
    - Multiple sheets by supplier and year
    - Organized sections with merged headers
    - Suspicious data tracking
    - Formula documentation
    - Executive summary sheet
    """

    @staticmethod
    def generate(
        valid_df: pd.DataFrame,
        suspicious_df: pd.DataFrame,
        output_dir: str = ".",
        supplier_filter: Optional[str] = None,
    ) -> str:
        """
        Generate professional Excel report with multiple sheets and formatting.

        Args:
            valid_df: Valid analysis results
            suspicious_df: Suspicious/filtered results
            output_dir: Output directory for the report
            supplier_filter: Supplier name used for filtering (for filename)

        Returns:
            Path to the generated Excel file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        supplier_suffix = f"_{supplier_filter}" if supplier_filter else ""
        filename = f"ROI_Analysis{supplier_suffix}_{timestamp}.xlsx"
        output_path = os.path.join(output_dir, filename)

        # Define column sections for better organization
        sections = {
            "Time & Volume": [
                "TOTAL_SHOTS",
                "PARTS_PRODUCED",
                "APPROVED_CT",
                "AVERAGE_CT",
                "AVG_CT_SLOW",
                "AVG_CT_FAST",
                "AVG_CT_WITHIN",
            ],
            "Uptime Metrics": [
                "PRODUCTION_TIME",
                "IDLE_TIME",
                "TOTAL_RUNTIME",
                "UPTIME_PERCENTAGE",
            ],
            "Shot Count Breakdown": [
                "WITHIN_SHOT_COUNT",
                "FASTER_SHOT_COUNT",
                "SLOWER_SHOT_COUNT",
                "WITHIN_SHOT_PCT",
                "FASTER_SHOT_PCT",
                "SLOWER_SHOT_PCT",
                "WITHIN_FROM_AVG_SHOT_COUNT",
                "PROCESS_STABILITY",
            ],
            "Used Hours": [
                "USED_HOURS",
                "USED_HOURS_FAST",
                "USED_HOURS_SLOW",
                "USED_HOURS_WITHIN",
            ],
            "Expected Hours": [
                "EXPECTED_HOURS",
                "EXPECTED_HOURS_FAST",
                "EXPECTED_HOURS_SLOW",
                "EXPECTED_HOURS_WITHIN",
            ],
            "Gained / Lost Time": ["GAIN_HOURS", "LOSS_HOURS", "HOURS_DIFF"],
            "Time Deviation": ["FASTER_TIME_SAVINGS_PCT", "SLOWER_TIME_OVERRUN_PCT"],
            "Efficiencies": [
                "TOOLING_EFFICIENCY",
                "FASTER_EFFICIENCY",
                "SLOWER_EFFICIENCY",
                "WITHIN_EFFICIENCY",
                "EFF_GAIN",
                "EFF_LOSS",
            ],
            "Status / Flags": ["STATUS", "DIFFERENCE"],
        }

        # Column order (supports daily, weekly, monthly aggregation)
        # Determine time column from data
        if "DATE" in valid_df.columns:
            time_col = "DATE"
        elif "WEEK" in valid_df.columns:
            time_col = "WEEK"
        elif "MONTH" in valid_df.columns:
            time_col = "MONTH"
        else:
            time_col = "DATE"  # fallback

        static_cols = ["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col]
        all_columns = static_cols[:]
        for cols in sections.values():
            all_columns.extend(cols)

        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            workbook = writer.book

            # Define formats
            section_format = workbook.add_format(
                {"bold": True, "bg_color": "#BDD7EE", "align": "center"}
            )
            header_format = workbook.add_format({"bold": True, "bg_color": "#DDEBF7"})
            number_format = workbook.add_format({"num_format": "#,##0.00"})
            text_format = workbook.add_format({"text_wrap": True})

            # 1. Valid data sheets (by supplier - all daily records in one sheet per supplier)
            used_sheet_names = set()

            if not valid_df.empty:
                for supplier_name, group_df in valid_df.groupby("SUPPLIER_NAME"):
                    base_name = ROIReportGenerator._clean_sheet_name(supplier_name)
                    safe_name = ROIReportGenerator._make_unique_sheet_name(
                        base_name, used_sheet_names
                    )

                    ROIReportGenerator._write_data_sheet(
                        writer,
                        workbook,
                        group_df,
                        safe_name,
                        all_columns,
                        static_cols,
                        sections,
                        section_format,
                        header_format,
                        number_format,
                        text_format,
                        supplier_name,
                    )

            # 2. Suspicious data sheet
            if not suspicious_df.empty:
                suspicious_df.to_excel(
                    writer, sheet_name="Suspicious_Data", index=False
                )
                worksheet = writer.sheets["Suspicious_Data"]

                # Apply basic formatting
                for col_idx, col in enumerate(suspicious_df.columns):
                    fmt = (
                        number_format
                        if col not in static_cols and col != "STATUS"
                        else text_format
                    )
                    worksheet.write(0, col_idx, col, header_format)
                    worksheet.set_column(col_idx, col_idx, 20, fmt)

            # 3. Formulas documentation sheet
            ROIReportGenerator._create_formulas_sheet(writer, workbook, header_format)

            # 4. Summary sheet
            if not valid_df.empty:
                ROIReportGenerator._create_summary_sheet(
                    writer, workbook, valid_df, header_format, number_format
                )

        logging.info(f"✅ Excel report generated: {output_path}")
        return output_path

    @staticmethod
    def _clean_sheet_name(name: str) -> str:
        """Clean sheet name for Excel compatibility."""
        name = re.sub(r"[^\w]", "_", name)  # Replace non-alphanumeric with underscore
        return name[:31]  # Excel max length

    @staticmethod
    def _make_unique_sheet_name(base_name: str, used: set) -> str:
        """Ensure unique Excel sheet name."""
        max_len = 31
        base_name = base_name[:max_len]
        candidate = base_name
        suffix_num = 1

        while candidate in used:
            suffix = f"_{suffix_num}"
            candidate = f"{base_name[: max_len - len(suffix)]}{suffix}"
            suffix_num += 1

        used.add(candidate)
        return candidate

    @staticmethod
    def _write_data_sheet(
        writer,
        workbook,
        group_df,
        sheet_name,
        all_columns,
        static_cols,
        sections,
        section_format,
        header_format,
        number_format,
        text_format,
        supplier_name,
    ):
        """Write formatted data sheet."""
        df_to_write = group_df[all_columns].copy()

        # Clean data
        for col in df_to_write.columns:
            if col not in static_cols and col != "STATUS":
                df_to_write[col] = pd.to_numeric(
                    df_to_write[col], errors="coerce"
                ).fillna(0)
            else:
                df_to_write[col] = df_to_write[col].fillna("")

        # Write data
        df_to_write.to_excel(
            writer, sheet_name=sheet_name, startrow=2, index=False, header=False
        )
        worksheet = writer.sheets[sheet_name]

        # Column headers
        for col_idx, col in enumerate(df_to_write.columns):
            fmt = (
                number_format
                if col not in static_cols and col != "STATUS"
                else text_format
            )
            worksheet.write(0, col_idx, col, header_format)
            worksheet.set_column(col_idx, col_idx, 25, fmt)

        # Section headers
        ROIReportGenerator._merge_section_headers(
            worksheet, len(static_cols), sections, section_format
        )

        # Add supplier reference
        worksheet.write(
            0, len(static_cols) + 12, f"Supplier: {supplier_name}", text_format
        )

    @staticmethod
    def _merge_section_headers(worksheet, start_col: int, sections: dict, fmt):
        """Create merged section headers."""
        current = start_col
        seen_spans = set()

        for section, cols in sections.items():
            start = current
            end = start + len(cols) - 1

            if end > start:
                span = (1, start, 1, end)
                if span not in seen_spans:
                    worksheet.merge_range(*span, f"🔹 {section}", fmt)
                    seen_spans.add(span)
            else:
                worksheet.write(1, start, f"🔹 {section}", fmt)

            current = end + 1

    @staticmethod
    def _create_formulas_sheet(writer, workbook, header_format):
        """Create formulas documentation sheet."""
        formulas_data = [
            ["Metric", "Description", "Python Logic", "Excel Formula (Example)"],
            ["APPROVED_CT", "Contracted cycle time", "From system data", ""],
            [
                "AVERAGE_CT",
                "Weighted average CT",
                "∑(CT × COUNT) / ∑COUNT",
                "=SUMPRODUCT(CT, COUNT)/SUM(COUNT)",
            ],
            [
                "AVG_CT_SLOW",
                "Weighted SLOW CT",
                "CT where CT > 105% APPROVED",
                "=SUMPRODUCT(CT_SLOW, COUNT_SLOW)/SUM(COUNT_SLOW)",
            ],
            [
                "AVG_CT_FAST",
                "Weighted FAST CT",
                "CT where CT < 95% APPROVED",
                "=SUMPRODUCT(CT_FAST, COUNT_FAST)/SUM(COUNT_FAST)",
            ],
            [
                "WITHIN_SHOT_COUNT",
                "Shots within ±5%",
                "|CT - APPROVED_CT| ≤ 5%",
                '=COUNTIFS(CT_RANGE,">="&0.95*APPROVED_CT,CT_RANGE,"<="&1.05*APPROVED_CT)',
            ],
            [
                "WITHIN_SHOT_PCT",
                "% of total shots",
                "WITHIN / TOTAL",
                "=WITHIN_SHOT_COUNT / TOTAL_SHOTS",
            ],
            [
                "USED_HOURS",
                "Total production time",
                "∑CT × COUNT / 3600",
                "=SUMPRODUCT(CT, COUNT)/3600",
            ],
            [
                "EXPECTED_HOURS",
                "Expected time",
                "APPROVED_CT × TOTAL / 3600",
                "=APPROVED_CT × TOTAL_SHOTS / 3600",
            ],
            [
                "GAIN_HOURS",
                "Time saved",
                "EXPECTED_FAST - USED_FAST",
                "=MAX(EXPECTED_FAST - USED_FAST, 0)",
            ],
            [
                "LOSS_HOURS",
                "Time lost",
                "USED_SLOW - EXPECTED_SLOW",
                "=MAX(USED_SLOW - EXPECTED_SLOW, 0)",
            ],
            [
                "TOOLING_EFFICIENCY",
                "Total efficiency %",
                "Approved_CT × Total / (Used × 3600)",
                "=(APPROVED_CT * TOTAL_SHOTS) / (USED_HOURS * 3600) × 100",
            ],
            [
                "EFF_GAIN",
                "Efficiency gain %",
                "FASTER_EFF / TOOLING_EFF",
                "=FASTER_EFFICIENCY / TOOLING_EFFICIENCY × 100",
            ],
            [
                "EFF_LOSS",
                "Efficiency loss %",
                "SLOWER_EFF / TOOLING_EFF",
                "=SLOWER_EFFICIENCY / TOOLING_EFFICIENCY × 100",
            ],
            [
                "STATUS",
                "Gain or Loss",
                "IF TOOLING_EFF < 100 → LOSS",
                '=IF(TOOLING_EFFICIENCY < 100, "LOSS", "GAIN")',
            ],
            [
                "PROCESS_STABILITY",
                "CT consistency %",
                "Shots within ±5% of average CT",
                "=(WITHIN_FROM_AVG_COUNT / TOTAL_SHOTS) × 100",
            ],
        ]

        formula_df = pd.DataFrame(formulas_data[1:], columns=formulas_data[0])
        formula_df.to_excel(writer, sheet_name="Formulas", index=False)

        formula_ws = writer.sheets["Formulas"]
        formula_ws.set_column(0, 3, 60)

        for col_idx, col in enumerate(formulas_data[0]):
            formula_ws.write(0, col_idx, col, header_format)

    @staticmethod
    def _create_summary_sheet(writer, workbook, valid_df, header_format, number_format):
        """Create summary analysis sheet (supports daily/weekly/monthly aggregation)."""
        # Determine time column from data
        if "DATE" in valid_df.columns:
            time_col = "DATE"
            time_label = "Days"
        elif "WEEK" in valid_df.columns:
            time_col = "WEEK"
            time_label = "Weeks"
        elif "MONTH" in valid_df.columns:
            time_col = "MONTH"
            time_label = "Months"
        else:
            time_col = "DATE"
            time_label = "Periods"

        # Calculate summary statistics
        summary_stats = {
            "Total Records": len(valid_df),
            "Unique Suppliers": valid_df["SUPPLIER_NAME"].nunique(),
            "Unique Equipment": valid_df["EQUIPMENT_CODE"].nunique(),
            f"{time_label} Covered": valid_df[time_col].nunique(),
            "Time Range": f"{valid_df[time_col].min()} to {valid_df[time_col].max()}",
            "Total Shots": valid_df["TOTAL_SHOTS"].sum(),
            "Total Parts": valid_df["PARTS_PRODUCED"].sum(),
            "Avg Tooling Efficiency": valid_df["TOOLING_EFFICIENCY"].mean(),
            "Avg Uptime %": valid_df["UPTIME_PERCENTAGE"].mean(),
            "Records with GAIN": len(valid_df[valid_df["STATUS"] == "GAIN"]),
            "Records with LOSS": len(valid_df[valid_df["STATUS"] == "LOSS"]),
            "Total Gain Hours": valid_df["GAIN_HOURS"].sum(),
            "Total Loss Hours": valid_df["LOSS_HOURS"].sum(),
        }

        summary_df = pd.DataFrame(
            list(summary_stats.items()), columns=["Metric", "Value"]
        )
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        summary_ws = writer.sheets["Summary"]
        summary_ws.set_column(0, 0, 30)
        summary_ws.set_column(1, 1, 20, number_format)

        for col_idx, col in enumerate(["Metric", "Value"]):
            summary_ws.write(0, col_idx, col, header_format)
