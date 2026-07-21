"""Insight generation helpers for weekly comparison PowerPoint presentations.

This module generates natural-language insight strings by comparing week-over-week
KPI values for efficiency, MTTR, MTBF, capacity, and cost metrics. Each generator
returns a human-readable summary suitable for bullet-point slides.
"""

from typing import Any, Callable, Dict, List, Optional


def generate_efficiency_insight(
    week1_kpis: Dict[str, Any], week2_kpis: Dict[str, Any]
) -> str:
    """Generate efficiency comparison insight.

    Args:
        week1_kpis: Week 1 KPIs dictionary
        week2_kpis: Week 2 KPIs dictionary

    Returns:
        Insight string describing efficiency change
    """
    eff1 = week1_kpis.get("runrate_efficiency", 0)
    eff2 = week2_kpis.get("runrate_efficiency", 0)
    eff_change = eff2 - eff1

    if abs(eff_change) > 0.1:
        direction = "increased" if eff_change > 0 else "decreased"
        return (
            f"Run Rate Efficiency {direction} from {eff1}% to {eff2}% "
            f"({eff_change:+.1f} percentage points)."
        )
    return f"Run Rate Efficiency remained stable at {eff2}%."


def generate_mttr_insight(
    week1_kpis: Dict[str, Any],
    week2_kpis: Dict[str, Any],
    calculate_percentage_change_fn: Callable[[float, float], str],
) -> Optional[str]:
    """Generate MTTR comparison insight.

    Args:
        week1_kpis: Week 1 KPIs dictionary
        week2_kpis: Week 2 KPIs dictionary
        calculate_percentage_change_fn: Function to calculate percentage change

    Returns:
        Insight string or None if no meaningful change
    """
    mttr1 = week1_kpis.get("runrate_mttr_minutes", 0)
    mttr2 = week2_kpis.get("runrate_mttr_minutes", 0)
    if mttr1 <= 0:
        return None

    mttr_pct = calculate_percentage_change_fn(mttr2, mttr1)
    if mttr2 < mttr1:
        return (
            f"MTTR improved by {mttr_pct}, indicating faster recovery "
            "from stops and quicker return to production."
        )
    elif mttr2 > mttr1:
        return (
            f"MTTR increased by {mttr_pct}, indicating longer "
            "recovery times from stops."
        )
    return None


def generate_mtbf_insight(
    week1_kpis: Dict[str, Any],
    week2_kpis: Dict[str, Any],
    calculate_percentage_change_fn: Callable[[float, float], str],
) -> Optional[str]:
    """Generate MTBF comparison insight.

    Args:
        week1_kpis: Week 1 KPIs dictionary
        week2_kpis: Week 2 KPIs dictionary
        calculate_percentage_change_fn: Function to calculate percentage change

    Returns:
        Insight string or None if no meaningful change
    """
    mtbf1 = week1_kpis.get("runrate_mtbf_minutes", 0)
    mtbf2 = week2_kpis.get("runrate_mtbf_minutes", 0)
    if mtbf1 <= 0:
        return None

    mtbf_pct = calculate_percentage_change_fn(mtbf2, mtbf1)
    if mtbf2 < mtbf1:
        return f"MTBF decreased by {mtbf_pct}, indicating more frequent failures."
    elif mtbf2 > mtbf1:
        return f"MTBF improved by {mtbf_pct}, indicating more reliable operation."
    return None


def generate_capacity_efficiency_insight(
    week1_kpis: Dict[str, Any], week2_kpis: Dict[str, Any]
) -> Optional[str]:
    """Generate capacity efficiency gain/loss insight.

    Args:
        week1_kpis: Week 1 KPIs dictionary
        week2_kpis: Week 2 KPIs dictionary

    Returns:
        Insight string or None if no meaningful change
    """
    eff_gain1 = week1_kpis.get("efficiency_gain_loss", 0)
    eff_gain2 = week2_kpis.get("efficiency_gain_loss", 0)
    if eff_gain1 == eff_gain2:
        return None

    if eff_gain1 < 0 and eff_gain2 > 0:
        improvement = eff_gain2 - eff_gain1
        return (
            f"Capacity Risk efficiency improved, shifting from a loss of "
            f"{abs(int(eff_gain1))} Parts to a gain of {int(eff_gain2)} Parts "
            f"({int(improvement)} Parts net improvement)."
        )
    elif eff_gain2 < eff_gain1:
        return (
            f"Capacity Risk efficiency declined, shifting from "
            f"{int(eff_gain1)} Parts to {int(eff_gain2)} Parts."
        )
    return None


def generate_cost_insight(
    week1_kpis: Dict[str, Any],
    week2_kpis: Dict[str, Any],
    calculate_percentage_change_fn: Callable[[float, float], str],
) -> Optional[str]:
    """Generate cost comparison insight.

    Args:
        week1_kpis: Week 1 KPIs dictionary
        week2_kpis: Week 2 KPIs dictionary
        calculate_percentage_change_fn: Function to calculate percentage change

    Returns:
        Insight string or None if no meaningful change
    """
    cost1 = week1_kpis.get("total_costs", 0)
    cost2 = week2_kpis.get("total_costs", 0)
    if cost1 <= 0:
        return None

    cost_pct = calculate_percentage_change_fn(cost2, cost1)
    if cost2 < cost1:
        return (
            f"Losses decreased by {cost_pct}, both in Total Incurred Costs "
            "and Parts Opportunity Lost."
        )
    elif cost2 > cost1:
        return (
            f"Losses increased by {cost_pct}, both in Total Incurred Costs "
            "and Parts Opportunity Lost."
        )
    return None


def generate_key_insights(
    equipment_code: str,
    week1_kpis: Dict[str, Any],
    week2_kpis: Dict[str, Any],
    week1_runrate: Dict[str, Any],
    week2_runrate: Dict[str, Any],
    week1_capacity: Dict[str, Any],
    week2_capacity: Dict[str, Any],
    calculate_percentage_change_fn: Callable[[float, float], str],
) -> List[str]:
    """Generate key insights text comparing the two weeks.

    Assembles individual metric insights into a single list for
    bullet-point presentation on a slide.

    Args:
        equipment_code: Equipment code (unused - kept for API compatibility)
        week1_kpis: Week 1 KPIs dictionary
        week2_kpis: Week 2 KPIs dictionary
        week1_runrate: Week 1 RunRate metrics (unused - kept for API compatibility)
        week2_runrate: Week 2 RunRate metrics (unused - kept for API compatibility)
        week1_capacity: Week 1 Capacity metrics (unused - kept for API compatibility)
        week2_capacity: Week 2 Capacity metrics (unused - kept for API compatibility)
        calculate_percentage_change_fn: Function to calculate percentage change

    Returns:
        List of insight strings
    """
    _ = equipment_code  # Unused - kept for API compatibility
    _ = week1_runrate  # Unused - kept for API compatibility
    _ = week2_runrate  # Unused - kept for API compatibility
    _ = week1_capacity  # Unused - kept for API compatibility
    _ = week2_capacity  # Unused - kept for API compatibility

    insights: List[str] = []

    # Efficiency comparison
    insights.append(generate_efficiency_insight(week1_kpis, week2_kpis))

    # MTTR comparison
    mttr_insight = generate_mttr_insight(
        week1_kpis, week2_kpis, calculate_percentage_change_fn
    )
    if mttr_insight:
        insights.append(mttr_insight)

    # MTBF comparison
    mtbf_insight = generate_mtbf_insight(
        week1_kpis, week2_kpis, calculate_percentage_change_fn
    )
    if mtbf_insight:
        insights.append(mtbf_insight)

    # Capacity efficiency gain/loss
    capacity_insight = generate_capacity_efficiency_insight(week1_kpis, week2_kpis)
    if capacity_insight:
        insights.append(capacity_insight)

    # Cost and parts opportunity lost
    cost_insight = generate_cost_insight(
        week1_kpis, week2_kpis, calculate_percentage_change_fn
    )
    if cost_insight:
        insights.append(cost_insight)

    return insights
