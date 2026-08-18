"""
Equipment-specific Five Whys analysis functions for root cause investigation.
This module contains the equipment analysis orchestrator and standalone functions
that generate each "why" explanation, root cause, and recommendations for a
specific piece of equipment compared to the rest of the fleet.
"""

import logging
from typing import Any, Dict, List

import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Why generators
# ---------------------------------------------------------------------------


def generate_why1_equipment(
    machine_id: str,
    metrics: Dict[str, Any],
) -> str:
    """Generate Why 1: immediate performance difference for the equipment."""
    if metrics.get("equipment_ct_mean", 0) > metrics.get("other_equipment_ct_mean", 0):
        ct_diff = metrics["equipment_ct_mean"] - metrics["other_equipment_ct_mean"]
        return "Equipment %s has %.1fs higher duration than other equipment" % (
            machine_id,
            ct_diff,
        )
    return (
        "Equipment %s shows performance variations compared to other equipment"
        % machine_id
    )


def generate_why2_equipment(
    machine_id: str,
    metrics: Dict[str, Any],
    equipment_data: pd.DataFrame,
) -> str:
    """Generate Why 2: specific operational challenges for the equipment."""
    return "Equipment %s has specific operational challenges" % machine_id


def generate_why3_equipment(
    machine_id: str,
    metrics: Dict[str, Any],
    equipment_data: pd.DataFrame,
) -> str:
    """Generate Why 3: process optimization needs."""
    return "Equipment %s requires process optimization" % machine_id


def generate_why4_equipment(
    machine_id: str,
    metrics: Dict[str, Any],
    equipment_data: pd.DataFrame,
) -> str:
    """Generate Why 4: maintenance and procedure improvement needs."""
    return "Equipment %s needs maintenance and procedure improvements" % machine_id


def generate_why5_equipment(
    machine_id: str,
    metrics: Dict[str, Any],
    equipment_data: pd.DataFrame,
) -> str:
    """Generate Why 5: systematic management improvement needs."""
    return "Equipment %s requires systematic management improvements" % machine_id


# ---------------------------------------------------------------------------
# Root cause and recommendations
# ---------------------------------------------------------------------------


def determine_root_cause_equipment(
    metrics: Dict[str, Any],
    equipment_data: pd.DataFrame,
) -> str:
    """Determine root cause string for equipment analysis."""
    return "Equipment-specific operational and maintenance optimization needed"


def generate_recommendations_equipment(
    metrics: Dict[str, Any],
    equipment_data: pd.DataFrame,
) -> List[str]:
    """Generate recommendations for equipment analysis."""
    return [
        "Implement equipment-specific maintenance program",
        "Optimize process parameters for this equipment",
        "Train operators on equipment-specific procedures",
        "Monitor equipment performance metrics",
        "Create equipment-specific standard operating procedures",
    ]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def five_whys_equipment(
    target_name: str,
    target_data: Dict[str, Any],
    target_df: pd.DataFrame,
    equipment_metrics_fn: Any,
    generic_fallback_fn: Any,
) -> Dict[str, Any]:
    """
    Apply the Five Whys methodology to equipment issues.

    Args:
        target_name: Display name of the target.
        target_data: Target metadata dict (must contain 'code').
        target_df: DataFrame already filtered to this target.
        equipment_metrics_fn: Callable to compute equipment comparison metrics.
        generic_fallback_fn: Callable returning a generic analysis dict.

    Returns:
        Complete Five Whys analysis dictionary.
    """
    analysis: Dict[str, Any] = {
        "target": target_name,
        "type": "Equipment",
        "whys": [],
        "root_cause": "",
        "supporting_data": {},
        "recommendations": [],
    }

    machine_id = target_data["code"]

    equipment_data = target_df[target_df["MACHINE_ID"] == machine_id]
    other_equipment_data = target_df[target_df["MACHINE_ID"] != machine_id]

    if len(equipment_data) == 0:
        return generic_fallback_fn(target_name)

    metrics = equipment_metrics_fn(equipment_data, other_equipment_data)

    analysis["whys"].append(generate_why1_equipment(machine_id, metrics))
    analysis["whys"].append(
        generate_why2_equipment(machine_id, metrics, equipment_data)
    )
    analysis["whys"].append(
        generate_why3_equipment(machine_id, metrics, equipment_data)
    )
    analysis["whys"].append(
        generate_why4_equipment(machine_id, metrics, equipment_data)
    )
    analysis["whys"].append(
        generate_why5_equipment(machine_id, metrics, equipment_data)
    )

    analysis["root_cause"] = determine_root_cause_equipment(metrics, equipment_data)
    analysis["supporting_data"] = metrics
    analysis["recommendations"] = generate_recommendations_equipment(
        metrics, equipment_data
    )

    return analysis
