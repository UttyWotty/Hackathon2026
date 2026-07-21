"""
Five Whys root cause analysis orchestrator for manufacturing issues.
This module contains the FiveWhysAnalysis class which applies the 5 Whys
methodology to Pareto analysis results. Heavy metric calculations, time-based
analysis, data-driven analysis, and equipment analysis are delegated to
dedicated submodules to keep this file focused on orchestration.
"""

import json
import logging
import os
import warnings
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from analysis.shared.constants import ShiftBoundaries

from .five_whys_comprehensive_metrics import (
    calculate_equipment_metrics,
    calculate_industry_metrics,
)
from .five_whys_data_driven import (
    calculate_comprehensive_metrics,
    generate_data_driven_analysis,
)
from .five_whys_equipment import five_whys_equipment

try:
    from .industry_standards import (
        IndustryStandardsAnalyzer,
        get_industry_comparison_chart_data,
    )
except ImportError:
    from industry_standards import (  # type: ignore[no-redef]
        IndustryStandardsAnalyzer,
        get_industry_comparison_chart_data,
    )

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

try:
    from .master_shot_table import fetch_data_from_snowflake, session
except ImportError:
    from master_shot_table import (  # type: ignore[no-redef]
        fetch_data_from_snowflake,
        session,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_TOP_N = 3
EQUIPMENT_ISSUE_RATE_THRESHOLD = 30
EFFICIENCY_CAP = 100
HIGH_PRIORITY_CUTOFF = 2


def _metric_summary(metrics: Dict[str, Any], actual_key: str) -> Dict[str, Any]:
    """Build a performance summary sub-dict for a single metric category."""
    return {
        "actual": metrics.get(actual_key, 0),
        "industry_benchmark": metrics.get("industry_benchmark", 0),
        "world_class": metrics.get("world_class_target", 0),
        "grade": metrics.get("performance_grade", "N/A"),
    }


def _grade_from_metrics(
    metrics_obj: Dict[str, Any],
    key: str = "performance_grade",
) -> str:
    """Extract a performance grade string with N/A fallback."""
    return metrics_obj.get(key, "N/A")


class FiveWhysAnalysis:
    """
    5 Whys Root Cause Analysis for manufacturing issues.

    Takes Pareto analysis results and applies systematic root cause
    investigation using the 5 Whys methodology.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        pareto_results: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.df = df.copy()
        self.pareto_results: Dict[str, Any] = pareto_results or {}
        self.root_causes: Dict[str, Any] = {}
        self.action_plans: Dict[str, Any] = {}
        self.tooling_family = self._determine_tooling_family()
        try:
            self.industry_analyzer: Optional[IndustryStandardsAnalyzer] = (
                IndustryStandardsAnalyzer(self.tooling_family)
            )
        except Exception as exc:
            logger.warning("Could not initialize industry analyzer: %s", exc)
            self.industry_analyzer = None
        self.setup_data()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _determine_tooling_family(self) -> str:
        """Determine tooling family from data."""
        if "TOOLING_FAMILY" in self.df.columns:
            mode = self.df["TOOLING_FAMILY"].mode()
            if not mode.empty:
                return mode.iloc[0]
        return "Injection Molding"

    def setup_data(self) -> bool:
        """Prepare data for 5 Whys analysis."""
        logger.info("Data prepared for 5 Whys analysis: %d records", len(self.df))
        logger.info("Tooling Family: %s", self.tooling_family)
        self._add_efficiency_column()
        self._add_temporal_columns()
        industry = calculate_industry_metrics(self.df, self.industry_analyzer)
        self.scrap_metrics = industry["scrap_metrics"]
        self.downtime_metrics = industry["downtime_metrics"]
        self.efficiency_metrics = industry["efficiency_metrics"]
        self.process_recommendations = industry["process_recommendations"]
        return True

    def _add_efficiency_column(self) -> None:
        """Add EFFICIENCY column if CT and APPROVED_CT are present."""
        if "CT" in self.df.columns and "APPROVED_CT" in self.df.columns:
            self.df["EFFICIENCY"] = (
                self.df["APPROVED_CT"] / self.df["CT"]
            ) * EFFICIENCY_CAP
            self.df["EFFICIENCY"] = self.df["EFFICIENCY"].clip(upper=EFFICIENCY_CAP)
            logger.info("Added EFFICIENCY column (Approved CT / Actual CT * 100)")
        else:
            logger.warning("Cannot calculate efficiency - missing CT or APPROVED_CT")

    def _add_temporal_columns(self) -> None:
        """Add SHIFT, DATE, and DAY_OF_WEEK columns as needed."""
        if "SHIFT" not in self.df.columns and "HOUR" in self.df.columns:
            self.df["SHIFT"] = self.df["HOUR"].apply(self._determine_shift)
            logger.info("Added SHIFT column based on HOUR")
        if "DATE" not in self.df.columns and "LOCAL_SHOT_TIME" in self.df.columns:
            self.df["DATE"] = pd.to_datetime(self.df["LOCAL_SHOT_TIME"]).dt.date
            logger.info("Added DATE column from LOCAL_SHOT_TIME")
        if (
            "DAY_OF_WEEK" not in self.df.columns
            and "LOCAL_SHOT_TIME" in self.df.columns
        ):
            self.df["DAY_OF_WEEK"] = pd.to_datetime(
                self.df["LOCAL_SHOT_TIME"]
            ).dt.day_name()
            logger.info("Added DAY_OF_WEEK column from LOCAL_SHOT_TIME")

    @staticmethod
    def _determine_shift(hour: int) -> str:
        """Determine shift based on hour."""
        if (
            ShiftBoundaries.DAY_START_HOUR
            <= hour
            < ShiftBoundaries.AFTERNOON_START_HOUR
        ):
            return "Day"
        if (
            ShiftBoundaries.AFTERNOON_START_HOUR
            <= hour
            < ShiftBoundaries.NIGHT_START_HOUR
        ):
            return "Afternoon"
        return "Night"

    # ------------------------------------------------------------------
    # Target identification
    # ------------------------------------------------------------------

    def identify_top_targets(self, top_n: int = DEFAULT_TOP_N) -> List[Dict[str, Any]]:
        """Identify top targets for root cause investigation."""
        logger.info("IDENTIFYING TOP TARGETS FOR ROOT CAUSE INVESTIGATION")
        targets: List[Dict[str, Any]] = []
        if "DAY_OF_WEEK" in self.df.columns:
            targets.extend(self._issue_targets("DAY_OF_WEEK", "Time", "Day", top_n))
        if len(targets) < top_n and "EQUIPMENT_CODE" in self.df.columns:
            targets.extend(
                self._issue_targets(
                    "EQUIPMENT_CODE",
                    "Equipment",
                    "Equipment",
                    top_n - len(targets),
                )
            )
        if len(targets) < top_n and "PART_NAME" in self.df.columns:
            targets.extend(
                self._issue_targets("PART_NAME", "Part", "Part", top_n - len(targets))
            )
        for i, t in enumerate(targets, 1):
            logger.info(
                "%d. %s: %d issues (%.1f%% rate)", i, t["name"], t["issues"], t["rate"]
            )
        return targets[:top_n]

    def _issue_targets(
        self,
        group_col: str,
        type_label: str,
        prefix: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Build issue-rate-ranked target dicts from a groupby column."""
        agg = (
            self.df.groupby(group_col).agg({"CT_ISSUE_FLAG": ["sum", "count"]}).round(2)
        )
        agg.columns = ["Issues", "Total_Shots"]
        agg["Issue_Rate"] = (agg["Issues"] / agg["Total_Shots"] * EFFICIENCY_CAP).round(
            2
        )
        agg = agg.sort_values("Issue_Rate", ascending=False)
        return [
            {
                "name": "%s %s" % (prefix, code),
                "code": code,
                "type": type_label,
                "issues": int(row["Issues"]),
                "total": int(row["Total_Shots"]),
                "rate": row["Issue_Rate"],
            }
            for code, row in agg.head(limit).iterrows()
        ]

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def apply_five_whys(
        self,
        target_name: str,
        target_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply 5 Whys methodology to a specific target."""
        logger.info("APPLYING 5 WHYS TO: %s", target_name)
        target_df = self._get_target_data(target_data)
        dispatch = {
            "equipment": self._five_whys_equipment,
            "part": self._five_whys_part,
            "time": self._five_whys_time,
        }
        handler = dispatch.get(target_data["type"].lower())
        if handler:
            analysis = handler(target_name, target_data, target_df)
        else:
            analysis = self._five_whys_generic(target_name)
        self.root_causes[target_name] = analysis
        return analysis

    def _get_target_data(self, target_data: Dict[str, Any]) -> pd.DataFrame:
        """Get data specific to the target."""
        col_map = {
            "equipment": "EQUIPMENT_CODE",
            "part": "PART_NAME",
            "time": "DAY_OF_WEEK",
        }
        col = col_map.get(target_data["type"].lower())
        if col:
            return self.df[self.df[col] == target_data["code"]]
        return self.df

    # ------------------------------------------------------------------
    # Analysis type dispatchers
    # ------------------------------------------------------------------

    def _five_whys_equipment(
        self,
        target_name: str,
        target_data: Dict[str, Any],
        target_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Delegate to five_whys_equipment module function."""
        return five_whys_equipment(
            target_name,
            target_data,
            target_df,
            calculate_equipment_metrics,
            self._five_whys_generic,
        )

    def _five_whys_part(
        self,
        target_name: str,
        target_data: Dict[str, Any],
        target_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Apply 5 Whys to part issues."""
        ct_stats = target_df["CT"].describe()
        avg_ct, std_ct = ct_stats["mean"], ct_stats["std"]
        whys = [
            "Part has inconsistent cycle times (avg: %.1fs +/- %.1fs)"
            % (avg_ct, std_ct)
        ]
        worst_equipment, worst_rate = self._worst_equipment_for_part(target_df)
        if worst_rate is not None and worst_rate > EQUIPMENT_ISSUE_RATE_THRESHOLD:
            whys.append(
                "Equipment %s struggles with this part (%.1f%% issues)"
                % (worst_equipment, worst_rate)
            )
        else:
            whys.append(
                "Part design or material properties cause processing challenges"
            )
        whys.extend(
            [
                "Part specifications exceed equipment capabilities or optimal parameters",
                "Part design not optimized for current equipment capabilities",
                "Lack of collaboration between design and manufacturing teams",
            ]
        )
        return {
            "target": target_name,
            "type": "Part",
            "whys": whys,
            "root_cause": "Design-manufacturing mismatch and insufficient process optimization",
            "supporting_data": {
                "avg_ct": avg_ct,
                "ct_std": std_ct,
                "worst_equipment": worst_equipment,
                "worst_equipment_rate": worst_rate,
            },
            "recommendations": [
                "Review part design for manufacturability",
                "Optimize process parameters for this specific part",
                "Improve design-manufacturing collaboration",
                "Consider equipment upgrades if needed",
            ],
        }

    @staticmethod
    def _worst_equipment_for_part(target_df: pd.DataFrame) -> tuple:
        """Return (worst_equipment_code, worst_rate) or (None, None)."""
        if "EQUIPMENT_CODE" not in target_df.columns:
            return None, None
        issues = target_df.groupby("EQUIPMENT_CODE")["CT_ISSUE_FLAG"].mean()
        return issues.idxmax(), issues.max() * EFFICIENCY_CAP

    def _five_whys_time(
        self,
        target_name: str,
        target_data: Dict[str, Any],
        target_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Apply 5 Whys to time-based issues via delegation."""
        day_name = target_data["code"]
        day_data = self.df[self.df["DAY_OF_WEEK"] == day_name]
        other_days = self.df[self.df["DAY_OF_WEEK"] != day_name]
        if len(day_data) == 0:
            return self._five_whys_generic(target_name)
        if len(other_days) == 0:
            return self._create_generic_analysis(
                target_name, "No comparison data available"
            )
        metrics = calculate_comprehensive_metrics(day_data, other_days, "day")
        return generate_data_driven_analysis(
            target_name, day_name, metrics, day_data, "day"
        )

    def _five_whys_generic(self, target_name: str) -> Dict[str, Any]:
        """Generic 5 Whys for unclassified target types."""
        return {
            "target": target_name,
            "type": "Generic",
            "whys": [
                "Process parameters are outside optimal ranges",
                "Equipment or tooling is not properly maintained",
                "Preventive maintenance schedule is inadequate",
                "Maintenance procedures are not standardized",
                "Lack of systematic approach to equipment management",
            ],
            "root_cause": "Inadequate systematic equipment and process management",
            "supporting_data": {},
            "recommendations": [
                "Implement systematic equipment management program",
                "Standardize maintenance procedures",
                "Establish clear process control parameters",
                "Create regular review and improvement cycles",
            ],
        }

    def _create_generic_analysis(
        self,
        target_name: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Create generic analysis, optionally noting a limiting reason."""
        whys = ["Performance issues identified for %s" % target_name]
        supporting: Dict[str, Any] = {}
        if reason:
            whys.append("Analysis limited due to: %s" % reason)
            supporting["reason"] = reason
        else:
            whys.append("Multiple contributing factors exist")
        whys.extend(
            [
                "Operational patterns affect performance",
                "Systematic issues are present",
                "Fundamental management improvements needed",
            ]
        )
        return {
            "target": target_name,
            "type": "Generic",
            "whys": whys,
            "root_cause": "Operational performance optimization needed",
            "supporting_data": supporting,
            "recommendations": [
                "Implement comprehensive performance monitoring",
                "Standardize operating procedures",
                "Enhance training programs",
                "Improve preventive maintenance",
                "Create performance review processes",
            ],
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_action_plan(
        self,
        analysis_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate comprehensive action plans with industry standards."""
        return [
            self._build_action_plan(name, analysis)
            for name, analysis in analysis_results.items()
        ]

    def _build_action_plan(
        self,
        target_name: str,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a single action plan entry from an analysis result."""
        items = [
            {
                "action": rec,
                "priority": "High" if i <= HIGH_PRIORITY_CUTOFF else "Medium",
                "timeline": "1-2 weeks" if i <= HIGH_PRIORITY_CUTOFF else "1-2 months",
            }
            for i, rec in enumerate(analysis.get("recommendations", []), 1)
        ]
        for rec in self.process_recommendations.get("high_priority", []):
            items.append(
                {
                    "action": "Industry Best Practice: %s" % rec,
                    "priority": "High",
                    "timeline": "1-2 weeks",
                }
            )
        return {
            "target": target_name,
            "root_cause": analysis.get("root_cause", "Unknown"),
            "action_items": items,
            "industry_insights": {
                "scrap_performance": _grade_from_metrics(self.scrap_metrics),
                "downtime_performance": _grade_from_metrics(self.downtime_metrics),
                "efficiency_performance": _grade_from_metrics(self.efficiency_metrics),
                "improvement_potential": {
                    k: getattr(self, "%s_metrics" % k).get("improvement_potential", 0)
                    for k in ("scrap", "downtime", "efficiency")
                },
            },
            "process_recommendations": self.process_recommendations.get(
                "process_specific", []
            ),
        }

    def generate_industry_comparison_report(self) -> Dict[str, Any]:
        """Generate industry comparison report."""
        try:
            chart_data = get_industry_comparison_chart_data(
                self.df, self.tooling_family
            )
            return {
                "tooling_family": self.tooling_family,
                "performance_summary": {
                    "scrap": _metric_summary(self.scrap_metrics, "scrap_rate"),
                    "downtime": _metric_summary(
                        self.downtime_metrics, "actual_downtime_rate"
                    ),
                    "efficiency": _metric_summary(
                        self.efficiency_metrics, "average_efficiency"
                    ),
                },
                "recommendations": self.process_recommendations,
                "chart_data": chart_data["chart_data"],
            }
        except Exception as exc:
            logger.warning("Error generating industry comparison report: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------

    def run_complete_analysis(self, top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
        """Run complete 5 Whys analysis with industry standards."""
        logger.info("RUNNING COMPLETE 5 WHYS ANALYSIS")
        top_targets = self.identify_top_targets(top_n)
        if not top_targets:
            logger.warning("No targets identified for analysis")
            return {}
        analysis_results: Dict[str, Any] = {}
        for target in top_targets:
            analysis_results[target["name"]] = self.apply_five_whys(
                target["name"], target
            )
        self.generate_action_plan(analysis_results)
        logger.info(
            "Analysis complete. Generated %d action plans", len(analysis_results)
        )
        return analysis_results


def main() -> None:
    """Main function to run 5 Whys analysis."""
    try:
        logger.info("Fetching data from Snowflake...")
        df = fetch_data_from_snowflake(session)
        if df.empty:
            logger.error("No data retrieved from Snowflake")
            return
        five_whys = FiveWhysAnalysis(df)
        action_plans = five_whys.run_complete_analysis(top_n=DEFAULT_TOP_N)
        from analysis.shared import get_output_dir

        output_dir = str(get_output_dir("rca"))
        five_whys_file = os.path.join(output_dir, "five_whys_results.json")
        with open(five_whys_file, "w") as f:
            json.dump(action_plans, f, indent=2, default=str)
        logger.info("5 Whys results saved to: %s", five_whys_file)
    except Exception as exc:
        logger.error("Error during analysis: %s", exc, exc_info=True)


if __name__ == "__main__":
    main()
