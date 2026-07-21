"""
ROI Analyzer - Main Orchestrator
==================================

Coordinates all ROI analysis modules and provides the main analysis interface.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd

from .classifier import CycleTimeClassifier
from .config import ROIAnalysisConfig
from .database import ROIDatabase
from .metrics import ROIMetricsCalculator
from .preprocessor import ROIPreprocessor
from .report_generator import ROIReportGenerator


class ROIAnalyzer:
    """
    Main orchestrator for ROI (Return on Investment) analysis.

    Coordinates database operations, data processing, classification,
    metrics calculation, and report generation.

    Attributes:
        config: Analysis configuration
        database: Database connection manager
        preprocessor: Data preprocessing handler
        classifier: Cycle time classifier
        metrics_calculator: Metrics calculation engine
    """

    def __init__(
        self, config: Optional[ROIAnalysisConfig] = None, schema: Optional[str] = None
    ):
        """
        Initialize the ROI Analyzer.

        Args:
            config: Configuration object with analysis parameters.
                   If None, uses default configuration.
            schema: Snowflake schema to use (overrides .env if provided)
        """
        self.config = config or ROIAnalysisConfig()

        # Set up logging
        self._setup_logging()

        # Initialize modules
        self.database = ROIDatabase(schema=schema)
        self.preprocessor = ROIPreprocessor()
        self.classifier = CycleTimeClassifier(self.config)
        self.metrics_calculator = ROIMetricsCalculator(self.config)

    def _setup_logging(self) -> None:
        """Set up logging using shared module logger (no root-logger pollution)."""
        from analysis.shared.logging import setup_module_logger

        self._logger = setup_module_logger("ROI_Analysis")

    def analyze(
        self,
        supplier_names: Optional[list] = None,
        equipment_codes: Optional[list] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        aggregation_level: str = "daily",
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Perform complete ROI analysis with configurable time aggregation.

        Args:
            supplier_names: Filter by supplier name(s) - list (optional)
            equipment_codes: Filter by equipment code(s) - list (optional)
            start_date: Start date in YYYY-MM-DD format (optional, defaults to 90 days ago)
            end_date: End date in YYYY-MM-DD format (optional, defaults to today)
            aggregation_level: Time aggregation - "daily", "weekly", or "monthly" (default: "daily")

        Returns:
            Tuple of (valid_results, suspicious_results)
        """
        self._logger.info(
            f"🚀 Starting ROI Analysis ({aggregation_level.title()} Aggregation)"
        )

        # Apply sensible date limits for daily aggregations to avoid overwhelming the system
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if not start_date:
            # Default to last 90 days for daily aggregation
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            self._logger.info(
                f"📅 No start date provided, defaulting to last 90 days: {start_date}"
            )

        # Warn if date range is very large (>180 days)
        date_diff = (
            datetime.strptime(end_date, "%Y-%m-%d")
            - datetime.strptime(start_date, "%Y-%m-%d")
        ).days

        if date_diff > 180:
            self._logger.warning(
                f"⚠️ Large date range detected ({date_diff} days). "
                f"Consider reducing range for better performance with daily aggregations."
            )

        self._logger.info(
            f"📅 Analysis period: {start_date} to {end_date} ({date_diff} days)"
        )

        # 1. Fetch data from database
        raw_data = self.database.fetch_data(
            supplier_names, equipment_codes, start_date, end_date
        )

        if raw_data.empty:
            self._logger.warning("⚠️ No data found for the specified criteria")
            return pd.DataFrame(), pd.DataFrame()

        # 2. Preprocess data
        processed_data = self.preprocessor.preprocess(raw_data)

        # 3. Calculate uptime metrics (production time vs idle time)
        processed_data = self.preprocessor.calculate_uptime_metrics(processed_data)

        # 4. Classify cycle times
        classified_data = self.classifier.classify(processed_data)

        # 5. Calculate metrics with specified aggregation level
        grouped_metrics = self.metrics_calculator.calculate_grouped_metrics(
            classified_data, aggregation_level=aggregation_level
        )

        # 6. Filter data into valid and suspicious
        valid_df, suspicious_df = self.metrics_calculator.filter_data(grouped_metrics)

        self._logger.info("✅ ROI Analysis completed successfully")
        return valid_df, suspicious_df

    def generate_excel_report(
        self,
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
        return ROIReportGenerator.generate(
            valid_df, suspicious_df, output_dir, supplier_filter
        )

    def generate_executive_summary(
        self,
        analysis_result: dict,
        output_dir: str = ".",
        llm_insights: Optional[str] = None,
    ) -> dict:
        """
        Generate executive summary HTML report.

        Args:
            analysis_result: Complete analysis result dictionary
            output_dir: Output directory for the summary
            llm_insights: Optional insights from LLM analysis

        Returns:
            dict: Generation result with path and status
        """
        from analysis.shared.summary_generator import get_summary_generator

        os.makedirs(output_dir, exist_ok=True)
        summary_path = os.path.join(
            output_dir,
            f"ROI_Executive_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
        )

        summary_gen = get_summary_generator()
        return summary_gen.generate_roi_summary(
            analysis_result=analysis_result,
            output_path=summary_path,
            llm_insights=llm_insights,
        )

    def generate_pdf_report(
        self,
        html_path: str,
        output_dir: str = ".",
    ) -> dict:
        """
        Convert HTML summary to PDF.

        Args:
            html_path: Path to HTML file to convert
            output_dir: Output directory for PDF

        Returns:
            dict: Generation result with path and status
        """
        from analysis.shared.pdf_generator import get_pdf_generator

        os.makedirs(output_dir, exist_ok=True)
        pdf_path = html_path.replace(".html", ".pdf")

        pdf_gen = get_pdf_generator()
        return pdf_gen.html_to_pdf(
            html_path=html_path,
            output_pdf_path=pdf_path,
            add_page_numbers=True,
            add_header=True,
        )

    def close_connections(self) -> None:
        """Close database connections."""
        self.database.close()
