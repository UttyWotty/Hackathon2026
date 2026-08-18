"""
Orchestrates the full Root Cause Analysis pipeline combining Pareto and 5 Whys.
Loads manufacturing shot data, runs Pareto analysis to surface top issues, applies
5 Whys to dig into root causes, and delegates report formatting to rca_report_formatter.
This module owns the pipeline sequencing; all report rendering lives elsewhere.
"""

import logging
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

from analysis.shared.error_handling import AnalysisError  # noqa: E402

from .five_whys_analysis import FiveWhysAnalysis  # noqa: E402
from .pareto_analysis_per_tool import ParetoAnalysis  # noqa: E402
from .rca_report_formatter import (  # noqa: E402
    calculate_expected_impact,
    get_priority_actions,
    print_comprehensive_report,
    save_report as save_report_to_file,
    summarize_five_whys,
)

# -- Column name constants -----------------------------------------------------
COL_MACHINE_ID = "MACHINE_ID"
COL_PRODUCT_NAME = "PRODUCT_NAME"
COL_DURATION_ISSUE_FLAG = "CT_ISSUE_FLAG"
COL_DURATION = "DURATION"
COL_DOWNTIME_EVENT = "DOWNTIME_EVENT"
COL_SCRAP_INDICATOR = "SCRAP_INDICATOR"
COL_SHOT_TIME = "SHOT_TIME"
COL_DAY_OF_WEEK = "DAY_OF_WEEK"

TOP_EQUIPMENT_LIMIT = 5
TOP_PARTS_LIMIT = 5
TOP_TIME_PATTERNS_LIMIT = 3
PERCENTAGE_MULTIPLIER = 100


class RootCauseAnalysisPipeline:
    """
    Orchestrates Pareto analysis, 5 Whys root cause analysis, and report
    generation for manufacturing shot data. Delegates report formatting
    and persistence to rca_report_formatter.
    """

    def __init__(
        self,
        df: Optional[pd.DataFrame] = None,
        equipment_filter: Optional[str] = None,
    ) -> None:
        """
        Initialize the analysis pipeline.

        Args:
            df: Manufacturing data. If None, data is fetched from Snowflake.
            equipment_filter: Specific equipment to analyze (e.g., "MX-7110").
        """
        self.df: Optional[pd.DataFrame] = df
        self.equipment_filter: Optional[str] = equipment_filter
        self.pareto_results: Dict[str, Any] = {}
        self.five_whys_results: Dict[str, Any] = {}
        self.action_plans: Dict[str, Any] = {}
        self.analysis_summary: Dict[str, Any] = {}

    def load_data(self) -> bool:
        """Load and prepare data for analysis, applying equipment filter."""
        logger.info("LOADING DATA FOR ROOT CAUSE ANALYSIS")

        if self.df is None:
            if not self._fetch_from_snowflake():
                return False

        if self.df is None or self.df.empty:
            logger.error("DataFrame is None or empty after loading")
            return False

        if self.equipment_filter:
            if not self._apply_equipment_filter():
                return False

        logger.info("Data loaded: %s records", f"{len(self.df):,}")
        logger.info(
            "Date range: %s to %s",
            self.df[COL_SHOT_TIME].min(),
            self.df[COL_SHOT_TIME].max(),
        )

        if COL_MACHINE_ID in self.df.columns:
            logger.info("Equipment: %d unique", self.df[COL_MACHINE_ID].nunique())
        if COL_PRODUCT_NAME in self.df.columns:
            logger.info("Parts: %d unique", self.df[COL_PRODUCT_NAME].nunique())

        return True

    def _fetch_from_snowflake(self) -> bool:
        """Fetch shot data from Snowflake or local CSV. Returns True on success."""
        from analysis.shared.local_source import is_local_data_enabled

        if is_local_data_enabled():
            logger.info("Serving RCA data from local dataset")
            from analysis.shared.local_source import query_rca_shots

            self.df = query_rca_shots(machine_id=self.equipment_filter)
            if self.df is None or self.df.empty:
                logger.error("Local dataset returned no RCA data")
                return False
            logger.info("Raw data loaded: %s records", f"{len(self.df):,}")
            return True

        logger.info("Fetching data from Snowflake...")
        try:
            from .shot_data import fetch_data_from_snowflake

            self.df = fetch_data_from_snowflake(session=None)

            if self.df is None:
                logger.error("Data fetch returned None")
                return False

            if self.df.empty:
                logger.error("Empty DataFrame retrieved from Snowflake")
                return False

            logger.info("Raw data loaded: %s records", f"{len(self.df):,}")
            return True

        except AnalysisError:
            raise
        except Exception as e:
            logger.error(
                "Error fetching data from Snowflake: %s", str(e), exc_info=True
            )
            return False

    def _apply_equipment_filter(self) -> bool:
        """Filter the dataframe to only the target equipment."""
        logger.info("Filtering for equipment: %s", self.equipment_filter)
        original_count = len(self.df)

        available_equipment = self.df[COL_MACHINE_ID].unique().tolist()
        logger.info("Available equipment codes: %s", available_equipment[:20])
        logger.info("Looking for: %s", self.equipment_filter)
        logger.info(
            "Equipment exists: %s",
            self.equipment_filter in available_equipment,
        )

        self.df = self.df[self.df[COL_MACHINE_ID] == self.equipment_filter].copy()
        filtered_count = len(self.df)
        logger.info(
            "Filtered from %s to %s records",
            f"{original_count:,}",
            f"{filtered_count:,}",
        )

        if filtered_count == 0:
            logger.error("No data found for equipment %s", self.equipment_filter)
            return False

        return True

    def run_pareto_analysis(self) -> ParetoAnalysis:
        """Run Pareto analysis to identify top issues."""
        logger.info("STEP 1: PARETO ANALYSIS")

        logger.info("Creating ParetoAnalysis object...")
        pareto = ParetoAnalysis(self.df)
        logger.info(
            "Pareto df has %d rows and columns: %s",
            len(pareto.df),
            pareto.df.columns.tolist(),
        )

        self.df = pareto.df
        logger.info(
            "After update, self.df has %d rows and columns: %s",
            len(self.df),
            self.df.columns.tolist(),
        )

        logger.info("Calculating issue rates...")
        self.pareto_results = self._build_pareto_results()

        logger.info("Pareto analysis complete")
        logger.info("Overall issue rate: %.1f%%", self.pareto_results["issue_rate"])
        logger.info("Downtime rate: %.1f%%", self.pareto_results["downtime_rate"])
        logger.info("Scrap rate: %.1f%%", self.pareto_results["scrap_rate"])

        return pareto

    def _build_pareto_results(self) -> Dict[str, Any]:
        """Compute aggregate Pareto result metrics from the current df."""
        row_count = len(self.df)
        return {
            "total_shots": row_count,
            "issue_rate": self._safe_rate(COL_DURATION_ISSUE_FLAG, row_count),
            "downtime_rate": self._safe_rate(COL_DOWNTIME_EVENT, row_count),
            "scrap_rate": self._safe_rate(COL_SCRAP_INDICATOR, row_count),
            "top_equipment": self._get_top_equipment(),
            "top_parts": self._get_top_parts(),
            "top_time_patterns": self._get_top_time_patterns(),
        }

    def _safe_rate(self, column: str, total: int) -> float:
        """Return percentage rate for a flag column, or 0 if missing."""
        if column not in self.df.columns or total == 0:
            return 0.0
        return (self.df[column].sum() / total) * PERCENTAGE_MULTIPLIER

    def _get_top_equipment(self) -> List[Dict[str, Any]]:
        """Get top equipment by issue rate."""
        if COL_MACHINE_ID not in self.df.columns:
            return []

        equipment_issues = (
            self.df.groupby(COL_MACHINE_ID)
            .agg({COL_DURATION_ISSUE_FLAG: "sum", COL_DURATION: "count"})
            .reset_index()
        )
        equipment_issues["Issue_Rate"] = (
            equipment_issues[COL_DURATION_ISSUE_FLAG]
            / equipment_issues[COL_DURATION]
            * PERCENTAGE_MULTIPLIER
        ).round(2)

        return (
            equipment_issues.sort_values("Issue_Rate", ascending=False)
            .head(TOP_EQUIPMENT_LIMIT)
            .to_dict("records")
        )

    def _get_top_parts(self) -> List[Dict[str, Any]]:
        """Get top parts by issue rate."""
        if COL_PRODUCT_NAME not in self.df.columns:
            return []

        part_issues = (
            self.df.groupby(COL_PRODUCT_NAME)
            .agg({COL_DURATION_ISSUE_FLAG: "sum", COL_DURATION: "count"})
            .reset_index()
        )
        part_issues["Issue_Rate"] = (
            part_issues[COL_DURATION_ISSUE_FLAG]
            / part_issues[COL_DURATION]
            * PERCENTAGE_MULTIPLIER
        ).round(2)

        return (
            part_issues.sort_values("Issue_Rate", ascending=False)
            .head(TOP_PARTS_LIMIT)
            .to_dict("records")
        )

    def _get_top_time_patterns(self) -> List[Dict[str, Any]]:
        """Get top time patterns by issue rate."""
        time_issues = (
            self.df.groupby(COL_DAY_OF_WEEK)
            .agg({COL_DURATION_ISSUE_FLAG: "sum", COL_DURATION: "count"})
            .reset_index()
        )
        time_issues["Issue_Rate"] = (
            time_issues[COL_DURATION_ISSUE_FLAG]
            / time_issues[COL_DURATION]
            * PERCENTAGE_MULTIPLIER
        ).round(2)

        return (
            time_issues.sort_values("Issue_Rate", ascending=False)
            .head(TOP_TIME_PATTERNS_LIMIT)
            .to_dict("records")
        )

    def run_five_whys_analysis(self, top_n: int = 3) -> FiveWhysAnalysis:
        """Run 5 Whys analysis on top issues identified by Pareto."""
        logger.info("STEP 2: 5 WHYS ROOT CAUSE ANALYSIS")

        five_whys = FiveWhysAnalysis(self.df)
        action_plans = five_whys.run_complete_analysis(top_n=top_n)

        self.five_whys_results = action_plans

        logger.info("action_plans type: %s", type(action_plans))
        if isinstance(action_plans, dict):
            logger.info("action_plans keys: %s", list(action_plans.keys()))
            for key, value in action_plans.items():
                logger.info("action_plans['%s'] type: %s", key, type(value))
                if isinstance(value, dict):
                    logger.info(
                        "action_plans['%s'] keys: %s",
                        key,
                        list(value.keys())[:10],
                    )

        logger.info("5 Whys analysis complete")
        logger.info("Generated %d action plans", len(action_plans))

        return five_whys

    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate and log the comprehensive analysis report."""
        logger.info("STEP 3: GENERATING COMPREHENSIVE REPORT")

        self.analysis_summary = {
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_summary": {
                "total_shots": len(self.df),
                "date_range": {
                    "start": self.df[COL_SHOT_TIME].min().strftime("%Y-%m-%d"),
                    "end": self.df[COL_SHOT_TIME].max().strftime("%Y-%m-%d"),
                },
                "equipment_count": (
                    self.df[COL_MACHINE_ID].nunique()
                    if COL_MACHINE_ID in self.df.columns
                    else 0
                ),
                "part_count": (
                    self.df[COL_PRODUCT_NAME].nunique()
                    if COL_PRODUCT_NAME in self.df.columns
                    else 0
                ),
            },
            "pareto_results": self.pareto_results,
            "five_whys_results": summarize_five_whys(self.five_whys_results),
            "priority_actions": get_priority_actions(self.five_whys_results),
            "expected_impact": calculate_expected_impact(self.pareto_results),
        }

        print_comprehensive_report(self.analysis_summary)

        return self.analysis_summary

    def save_report(self, filename: Optional[str] = None) -> str:
        """Delegate report persistence to rca_report_formatter."""
        return save_report_to_file(self.analysis_summary, filename)

    def run_complete_pipeline(
        self,
        top_n: int = 3,
        save_report: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Run the complete root cause analysis pipeline end-to-end.

        Args:
            top_n: Number of top targets for 5 Whys analysis.
            save_report: Whether to save the report to a JSON file.

        Returns:
            Dict with pareto, five_whys, and report keys, or None on failure.
        """
        logger.info("STARTING COMPLETE ROOT CAUSE ANALYSIS PIPELINE")

        try:
            if not self.load_data():
                logger.error("Failed to load data. Pipeline cannot continue.")
                return None

            pareto = self.run_pareto_analysis()
            five_whys = self.run_five_whys_analysis(top_n=top_n)
            report = self.generate_comprehensive_report()

            if save_report:
                self.save_report()

            logger.info("PIPELINE COMPLETE")
            logger.info("Next Steps:")
            logger.info("  1. Review high-priority actions")
            logger.info("  2. Assign action owners")
            logger.info("  3. Implement immediate actions (1-2 weeks)")
            logger.info("  4. Track progress monthly")
            logger.info("  5. Re-run analysis in 3 months")

            return {
                "pareto": pareto,
                "five_whys": five_whys,
                "report": report,
            }

        except AnalysisError:
            raise
        except Exception as e:
            logger.error("Error in pipeline: %s", str(e), exc_info=True)
            return None


def main() -> None:
    """Main function to run the complete pipeline."""
    logger.info("ROOT CAUSE ANALYSIS PIPELINE")
    logger.info("=" * 60)

    logger.info("Complete Analysis (All Equipment)")
    pipeline = RootCauseAnalysisPipeline()
    results = pipeline.run_complete_pipeline(top_n=3)

    if results:
        logger.info("Pipeline completed successfully")
        logger.info("Ready to implement action plans")
    else:
        logger.error("Pipeline failed. Check error messages above.")


if __name__ == "__main__":
    main()
