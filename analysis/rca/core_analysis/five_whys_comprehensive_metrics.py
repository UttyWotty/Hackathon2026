"""
Industry-standard and equipment-comparison metric calculations for Five Whys.
This module provides calculate_industry_metrics for benchmarking scrap, downtime,
and efficiency against industry standards, and calculate_equipment_metrics for
comparing a single equipment unit against the rest of the fleet.
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Industry metrics (called once during setup_data)
# ---------------------------------------------------------------------------


def calculate_industry_metrics(
    df: pd.DataFrame,
    industry_analyzer: Optional[Any],
) -> Dict[str, Any]:
    """
    Calculate industry-standard scrap, downtime, and efficiency metrics.

    Returns a dict with keys: scrap_metrics, downtime_metrics,
    efficiency_metrics, process_recommendations.
    """
    default_result: Dict[str, Any] = {
        "scrap_metrics": {"performance_grade": "N/A"},
        "downtime_metrics": {"performance_grade": "N/A"},
        "efficiency_metrics": {"performance_grade": "N/A"},
        "process_recommendations": {"high_priority": [], "process_specific": []},
    }

    try:
        logger.info("Calculating industry standard metrics...")
        if industry_analyzer is None:
            logger.warning("Industry analyzer not available, using default metrics")
            return default_result

        scrap = industry_analyzer.calculate_scrap_metrics(df)
        downtime = industry_analyzer.calculate_downtime_metrics(df)
        efficiency = industry_analyzer.calculate_efficiency_metrics(df)
        recommendations = industry_analyzer.generate_process_specific_recommendations(
            scrap, downtime, efficiency
        )

        logger.info(
            "Industry metrics calculated: Scrap %.2f%% (%s), "
            "Downtime %.2f%% (%s), Efficiency %.2f%% (%s)",
            scrap.get("scrap_rate", 0),
            scrap.get("performance_grade", "N/A"),
            downtime.get("actual_downtime_rate", 0),
            downtime.get("performance_grade", "N/A"),
            efficiency.get("average_efficiency", 0),
            efficiency.get("performance_grade", "N/A"),
        )

        return {
            "scrap_metrics": scrap,
            "downtime_metrics": downtime,
            "efficiency_metrics": efficiency,
            "process_recommendations": recommendations,
        }
    except Exception as exc:
        logger.warning("Error calculating industry metrics: %s", exc)
        return default_result


# ---------------------------------------------------------------------------
# Equipment-comparison metrics
# ---------------------------------------------------------------------------


def calculate_equipment_metrics(
    equipment_data: pd.DataFrame,
    other_equipment_data: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Calculate comprehensive metrics comparing one equipment unit to others.

    Args:
        equipment_data: Data for the specific equipment.
        other_equipment_data: Data for all other equipment.

    Returns:
        Equipment comparison metrics dictionary.
    """
    metrics: Dict[str, Any] = {
        "equipment_count": len(equipment_data),
        "other_equipment_count": len(other_equipment_data),
    }

    if "CT" in equipment_data.columns:
        metrics["equipment_ct_mean"] = equipment_data["CT"].mean()
        metrics["equipment_ct_std"] = equipment_data["CT"].std()
        metrics["other_equipment_ct_mean"] = other_equipment_data["CT"].mean()
        metrics["other_equipment_ct_std"] = other_equipment_data["CT"].std()
        if "CT_ISSUE_FLAG" in equipment_data.columns:
            metrics["equipment_ct_issues"] = equipment_data["CT_ISSUE_FLAG"].sum()
            metrics["other_equipment_ct_issues"] = other_equipment_data[
                "CT_ISSUE_FLAG"
            ].sum()

    if "EFFICIENCY" in equipment_data.columns:
        metrics["equipment_efficiency_mean"] = equipment_data["EFFICIENCY"].mean()
        metrics["other_equipment_efficiency_mean"] = other_equipment_data[
            "EFFICIENCY"
        ].mean()

    return metrics
