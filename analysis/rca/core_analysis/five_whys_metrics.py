"""
Basic metric calculation functions for the Five Whys root cause analysis.
These functions compute cycle time, efficiency, downtime, scrap, shift, hour,
equipment, and day-level metrics for day-vs-other-days comparisons.
All functions accept DataFrames and return dictionaries of computed values.
"""

import logging
from typing import Any, Dict

import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds / constants
# ---------------------------------------------------------------------------
CT_ISSUE_DOWNTIME_MULTIPLIER = 5
CT_ISSUE_SCRAP_RATE = 0.1
CT_VARIANCE_SCRAP_RATE = 0.05
CT_VARIANCE_SIGMA = 2
CT_VARIANCE_DOWNTIME_MULTIPLIER = 3


# ---------------------------------------------------------------------------
# Basic / CT / Efficiency / Downtime
# ---------------------------------------------------------------------------


def calculate_basic_statistics(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, int]:
    """Return record counts for the target day and comparison group."""
    return {
        "day_count": len(day_data),
        "other_days_count": len(other_days_data),
    }


def calculate_ct_metrics(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, Any]:
    """Return cycle-time means, variances, and issue counts."""
    metrics: Dict[str, Any] = {}
    if "CT" not in day_data.columns:
        logger.warning("No CT column found")
        return metrics

    metrics["avg_ct_day"] = day_data["CT"].mean()
    metrics["avg_ct_other"] = (
        other_days_data["CT"].mean() if len(other_days_data) > 0 else 0
    )
    metrics["ct_variance_day"] = day_data["CT"].var() if len(day_data) > 1 else 0
    metrics["ct_variance_other"] = (
        other_days_data["CT"].var() if len(other_days_data) > 1 else 0
    )

    if "CT_ISSUE_FLAG" in day_data.columns:
        metrics["ct_issues_day"] = day_data["CT_ISSUE_FLAG"].sum()
        metrics["ct_issues_other"] = (
            other_days_data["CT_ISSUE_FLAG"].sum() if len(other_days_data) > 0 else 0
        )
    else:
        logger.warning("No CT_ISSUE_FLAG column found, using 0 as default")
        metrics["ct_issues_day"] = 0
        metrics["ct_issues_other"] = 0

    logger.info(
        "CT Analysis - Day avg: %.2fs, Other avg: %.2fs",
        metrics["avg_ct_day"],
        metrics["avg_ct_other"],
    )
    return metrics


def calculate_efficiency_metrics(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, float]:
    """Return average efficiency for the target day and comparison group."""
    metrics: Dict[str, float] = {}
    if "EFFICIENCY" not in day_data.columns:
        logger.warning("No EFFICIENCY column found")
        return metrics

    metrics["avg_efficiency_day"] = day_data["EFFICIENCY"].mean()
    metrics["avg_efficiency_other"] = (
        other_days_data["EFFICIENCY"].mean() if len(other_days_data) > 0 else 0
    )
    logger.info(
        "Efficiency - Day avg: %.2f%%, Other avg: %.2f%%",
        metrics["avg_efficiency_day"],
        metrics["avg_efficiency_other"],
    )
    return metrics


def calculate_downtime_metrics(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, float]:
    """Return downtime totals/averages or estimates from CT deviations."""
    metrics: Dict[str, float] = {}
    if "DOWNTIME" in day_data.columns:
        metrics["total_downtime_day"] = day_data["DOWNTIME"].sum()
        metrics["total_downtime_other"] = (
            other_days_data["DOWNTIME"].sum() if len(other_days_data) > 0 else 0
        )
        metrics["avg_downtime_day"] = day_data["DOWNTIME"].mean()
        metrics["avg_downtime_other"] = (
            other_days_data["DOWNTIME"].mean() if len(other_days_data) > 0 else 0
        )
        logger.info(
            "Downtime - Day total: %.2f, Other total: %.2f",
            metrics["total_downtime_day"],
            metrics["total_downtime_other"],
        )
    else:
        logger.info("Calculating downtime from CT deviations...")
        if "CT_ISSUE_FLAG" in day_data.columns:
            metrics["estimated_downtime_day"] = (
                day_data["CT_ISSUE_FLAG"].sum() * CT_ISSUE_DOWNTIME_MULTIPLIER
            )
            metrics["estimated_downtime_other"] = (
                other_days_data["CT_ISSUE_FLAG"].sum() * CT_ISSUE_DOWNTIME_MULTIPLIER
                if len(other_days_data) > 0
                else 0
            )
            logger.info(
                "Estimated Downtime - Day: %.0f min, Other: %.0f min",
                metrics["estimated_downtime_day"],
                metrics["estimated_downtime_other"],
            )
        else:
            ct_threshold = day_data["CT"].mean() + (
                CT_VARIANCE_SIGMA * day_data["CT"].std()
            )
            downtime_events = day_data[day_data["CT"] > ct_threshold].shape[0]
            metrics["estimated_downtime_day"] = (
                downtime_events * CT_VARIANCE_DOWNTIME_MULTIPLIER
            )
            logger.info(
                "Estimated Downtime from CT variance: %.0f min",
                metrics["estimated_downtime_day"],
            )
    return metrics


# ---------------------------------------------------------------------------
# Scrap helpers
# ---------------------------------------------------------------------------


def calculate_scrap_rate(scrap_count: int, total_count: int) -> float:
    """Return scrap rate as a percentage."""
    return (scrap_count / total_count) * 100 if total_count > 0 else 0.0


def calculate_scrap_from_column(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, float]:
    """Compute scrap metrics directly from a SCRAP column."""
    metrics: Dict[str, float] = {
        "total_scrap_day": day_data["SCRAP"].sum(),
        "total_scrap_other": other_days_data["SCRAP"].sum(),
    }
    metrics["scrap_rate_day"] = calculate_scrap_rate(
        int(metrics["total_scrap_day"]), len(day_data)
    )
    metrics["scrap_rate_other"] = calculate_scrap_rate(
        int(metrics["total_scrap_other"]), len(other_days_data)
    )
    logger.info(
        "Scrap - Day rate: %.2f%%, Other rate: %.2f%%",
        metrics["scrap_rate_day"],
        metrics["scrap_rate_other"],
    )
    return metrics


def calculate_scrap_from_ct_issues(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, float]:
    """Estimate scrap metrics from CT_ISSUE_FLAG column."""
    estimated_scrap_day = int(day_data["CT_ISSUE_FLAG"].sum() * CT_ISSUE_SCRAP_RATE)
    estimated_scrap_other = int(
        other_days_data["CT_ISSUE_FLAG"].sum() * CT_ISSUE_SCRAP_RATE
        if len(other_days_data) > 0
        else 0
    )
    metrics: Dict[str, float] = {
        "estimated_scrap_day": estimated_scrap_day,
        "estimated_scrap_other": estimated_scrap_other,
    }
    metrics["scrap_rate_day"] = calculate_scrap_rate(estimated_scrap_day, len(day_data))
    metrics["scrap_rate_other"] = calculate_scrap_rate(
        estimated_scrap_other, len(other_days_data)
    )
    logger.info(
        "Estimated Scrap - Day: %d parts (%.2f%%), Other: %d parts (%.2f%%)",
        metrics["estimated_scrap_day"],
        metrics["scrap_rate_day"],
        metrics["estimated_scrap_other"],
        metrics["scrap_rate_other"],
    )
    return metrics


def calculate_scrap_from_ct_variance(
    day_data: pd.DataFrame,
) -> Dict[str, float]:
    """Estimate scrap metrics from cycle-time variance."""
    ct_threshold = day_data["CT"].mean() + (CT_VARIANCE_SIGMA * day_data["CT"].std())
    scrap_events = day_data[day_data["CT"] > ct_threshold].shape[0]
    estimated_scrap_day = int(scrap_events * CT_VARIANCE_SCRAP_RATE)
    metrics: Dict[str, float] = {"estimated_scrap_day": estimated_scrap_day}
    metrics["scrap_rate_day"] = calculate_scrap_rate(estimated_scrap_day, len(day_data))
    logger.info(
        "Estimated Scrap from CT variance: %d parts (%.2f%%)",
        metrics["estimated_scrap_day"],
        metrics["scrap_rate_day"],
    )
    return metrics


def calculate_scrap_metrics(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, float]:
    """Dispatch to the appropriate scrap calculation method."""
    if "SCRAP" in day_data.columns:
        return calculate_scrap_from_column(day_data, other_days_data)

    logger.info("Calculating scrap from CT issues...")
    if "CT_ISSUE_FLAG" in day_data.columns:
        return calculate_scrap_from_ct_issues(day_data, other_days_data)

    return calculate_scrap_from_ct_variance(day_data)


# ---------------------------------------------------------------------------
# Shift / Hour / Equipment groupby analyses
# ---------------------------------------------------------------------------


def calculate_shift_analysis(day_data: pd.DataFrame) -> Dict[str, Any]:
    """Group target-day data by SHIFT and return CT/issue aggregations."""
    if "SHIFT" not in day_data.columns:
        logger.warning("No SHIFT column found")
        return {}

    try:
        agg_dict: Dict[str, Any] = {"CT": ["mean", "std", "count"]}
        if "CT_ISSUE_FLAG" in day_data.columns:
            agg_dict["CT_ISSUE_FLAG"] = "sum"
        shift_analysis = day_data.groupby("SHIFT").agg(agg_dict).round(2)
        logger.info("Shift Analysis: %d shifts found", len(shift_analysis))
        return {"shift_analysis": shift_analysis}
    except Exception as exc:
        logger.error("Error in shift analysis: %s", exc)
        return {}


def calculate_hour_analysis(day_data: pd.DataFrame) -> Dict[str, Any]:
    """Group target-day data by HOUR and return CT/issue aggregations."""
    if "HOUR" not in day_data.columns:
        logger.warning("No HOUR column found")
        return {}

    try:
        agg_dict: Dict[str, Any] = {"CT": ["mean", "std", "count"]}
        if "CT_ISSUE_FLAG" in day_data.columns:
            agg_dict["CT_ISSUE_FLAG"] = "sum"
        hour_analysis = day_data.groupby("HOUR").agg(agg_dict).round(2)
        logger.info("Hour Analysis: %d hours found", len(hour_analysis))
        return {"hour_analysis": hour_analysis}
    except Exception as exc:
        logger.error("Error in hour analysis: %s", exc)
        return {}


def calculate_equipment_analysis(day_data: pd.DataFrame) -> Dict[str, Any]:
    """Group target-day data by EQUIPMENT_CODE and return CT/issue aggregations."""
    if "EQUIPMENT_CODE" not in day_data.columns:
        logger.warning("No EQUIPMENT_CODE column found")
        return {}

    try:
        agg_dict: Dict[str, Any] = {"CT": ["mean", "std"]}
        if "CT_ISSUE_FLAG" in day_data.columns:
            agg_dict["CT_ISSUE_FLAG"] = "sum"
        equipment_issues = day_data.groupby("EQUIPMENT_CODE").agg(agg_dict).round(2)
        logger.info("Equipment Analysis: %d equipment found", len(equipment_issues))
        return {"equipment_analysis": equipment_issues}
    except Exception as exc:
        logger.error("Error in equipment analysis: %s", exc)
        return {}


def calculate_day_metrics(
    day_data: pd.DataFrame,
    other_days_data: pd.DataFrame,
) -> Dict[str, Any]:
    """Aggregate all day-level metric calculations into a single dictionary."""
    logger.info(
        "Calculating metrics for %d day records vs %d other records",
        len(day_data),
        len(other_days_data),
    )
    metrics: Dict[str, Any] = {}
    metrics.update(calculate_basic_statistics(day_data, other_days_data))
    metrics.update(calculate_ct_metrics(day_data, other_days_data))
    metrics.update(calculate_efficiency_metrics(day_data, other_days_data))
    metrics.update(calculate_downtime_metrics(day_data, other_days_data))
    metrics.update(calculate_scrap_metrics(day_data, other_days_data))
    metrics.update(calculate_shift_analysis(day_data))
    metrics.update(calculate_hour_analysis(day_data))
    metrics.update(calculate_equipment_analysis(day_data))
    return metrics
