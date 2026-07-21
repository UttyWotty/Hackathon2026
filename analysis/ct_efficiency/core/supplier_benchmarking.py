"""
Supplier Benchmarking.

This module contains functions for benchmarking suppliers based on
cycle time efficiency and tool consistency.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
from typing import Dict, List

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ..models import (
    MIN_TOOLS_FOR_CONSISTENCY,
    SupplierBenchmark,
    classify_supplier_tier,
)

logger = logging.getLogger(__name__)


# ==================== Supplier Benchmarking ==================== #


def benchmark_suppliers(tool_metrics: pd.DataFrame) -> List[SupplierBenchmark]:
    """Perform comprehensive supplier benchmarking analysis.

    Args:
        tool_metrics: DataFrame with aggregated tool metrics including
                     normalized_efficiency and supplier information

    Returns:
        List[SupplierBenchmark]: List of supplier benchmark results, sorted by rank
    """
    logger.info("Performing supplier benchmarking analysis...")

    # Group by supplier
    supplier_groups = tool_metrics.groupby("SUPPLIER_NAME")

    benchmarks = []

    for supplier_name, group in supplier_groups:
        # Calculate mean normalized efficiency
        mean_norm_eff = group["normalized_efficiency"].mean()

        # Calculate tool consistency score
        consistency = calculate_tool_consistency(group)

        # Count total tools
        total_tools = len(group)

        # Create benchmark object (rank and tier will be assigned later)
        benchmark = SupplierBenchmark(
            supplier_id=str(supplier_name),
            supplier_name=str(supplier_name),
            mean_normalized_efficiency=round(mean_norm_eff, 4),
            tool_consistency_score=round(consistency, 2),
            total_tools=total_tools,
            performance_rank=0,  # Will be set after ranking
            tier_classification="",  # Will be set after ranking
            adjusted_score=0.0,  # Will be calculated
        )

        benchmarks.append(benchmark)

    # Rank suppliers
    benchmarks = rank_suppliers(benchmarks)

    # Assign tiers
    benchmarks = assign_supplier_tiers(benchmarks)

    logger.info(f"✅ Benchmarked {len(benchmarks)} suppliers")

    return benchmarks


def calculate_tool_consistency(supplier_tools: pd.DataFrame) -> float:
    """Calculate consistency score for a supplier's tools.

    Consistency is measured by the inverse coefficient of variation (CV).
    Lower CV = higher consistency = higher score.

    Args:
        supplier_tools: DataFrame with tool metrics for one supplier

    Returns:
        float: Consistency score (0-100, higher is better)
    """
    if len(supplier_tools) < MIN_TOOLS_FOR_CONSISTENCY:
        # Not enough tools for meaningful consistency measurement
        return 50.0  # Neutral score

    # Calculate coefficient of variation for efficiency
    mean_eff = supplier_tools["mean_efficiency"].mean()
    std_eff = supplier_tools["mean_efficiency"].std()

    if mean_eff == 0:
        return 0.0

    cv = (std_eff / abs(mean_eff)) * 100  # Coefficient of variation as percentage

    # Convert CV to consistency score (inverse relationship)
    # CV of 0% = score 100, CV of 50%+ = score 0
    consistency_score = max(0, 100 - (cv * 2))

    return consistency_score


def rank_suppliers(benchmarks: List[SupplierBenchmark]) -> List[SupplierBenchmark]:
    """Rank suppliers based on adjusted performance score.

    Adjusted score considers both efficiency and consistency.

    Args:
        benchmarks: List of SupplierBenchmark objects

    Returns:
        List[SupplierBenchmark]: Ranked list (best to worst)
    """
    logger.info("Ranking suppliers based on performance...")

    # Calculate adjusted scores
    for benchmark in benchmarks:
        # Weighted score: 70% efficiency + 30% consistency
        adjusted = 0.7 * benchmark.mean_normalized_efficiency + 0.3 * (
            benchmark.tool_consistency_score / 100
        )
        benchmark.adjusted_score = round(adjusted, 4)

    # Sort by adjusted score (descending)
    benchmarks.sort(key=lambda x: x.adjusted_score, reverse=True)

    # Assign ranks
    for rank, benchmark in enumerate(benchmarks, start=1):
        benchmark.performance_rank = rank

    return benchmarks


def assign_supplier_tiers(
    benchmarks: List[SupplierBenchmark],
) -> List[SupplierBenchmark]:
    """Assign tier classifications to suppliers based on their ranking.

    Args:
        benchmarks: Ranked list of SupplierBenchmark objects

    Returns:
        List[SupplierBenchmark]: List with tier classifications assigned
    """
    logger.info("Assigning supplier tier classifications...")

    # Convert adjusted scores to 0-1 scale for tier classification
    scores = [b.adjusted_score for b in benchmarks]
    if len(scores) > 0:
        min_score = min(scores)
        max_score = max(scores)
        score_range = max_score - min_score if max_score > min_score else 1.0

        for benchmark in benchmarks:
            # Normalize to 0-1 scale
            normalized = (benchmark.adjusted_score - min_score) / score_range
            # Classify tier
            tier = classify_supplier_tier(normalized)
            benchmark.tier_classification = tier

    return benchmarks


def generate_supplier_summary(benchmarks: List[SupplierBenchmark]) -> Dict:
    """Generate summary statistics for supplier benchmarking.

    Args:
        benchmarks: List of SupplierBenchmark objects

    Returns:
        Dict: Summary statistics and insights
    """
    if not benchmarks:
        return {"total_suppliers": 0}

    # Count suppliers by tier
    tier_counts = {}
    for benchmark in benchmarks:
        tier = benchmark.tier_classification
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Calculate statistics
    efficiencies = [b.mean_normalized_efficiency for b in benchmarks]
    consistencies = [b.tool_consistency_score for b in benchmarks]

    summary = {
        "total_suppliers": len(benchmarks),
        "tier_distribution": tier_counts,
        "mean_efficiency": round(float(np.mean(efficiencies)), 2),
        "mean_consistency": round(float(np.mean(consistencies)), 2),
        "top_supplier": (
            {
                "name": benchmarks[0].supplier_name,
                "efficiency": round(benchmarks[0].mean_normalized_efficiency, 2),
                "consistency": round(benchmarks[0].tool_consistency_score, 2),
                "tier": benchmarks[0].tier_classification,
            }
            if benchmarks
            else None
        ),
        "bottom_supplier": (
            {
                "name": benchmarks[-1].supplier_name,
                "efficiency": round(benchmarks[-1].mean_normalized_efficiency, 2),
                "consistency": round(benchmarks[-1].tool_consistency_score, 2),
                "tier": benchmarks[-1].tier_classification,
            }
            if benchmarks
            else None
        ),
    }

    return summary


def get_supplier_comparison(
    benchmarks: List[SupplierBenchmark], supplier_names: List[str] = None
) -> List[Dict]:
    """Get comparison data for specific suppliers.

    Args:
        benchmarks: List of SupplierBenchmark objects
        supplier_names: Optional list of supplier names to compare

    Returns:
        List[Dict]: Comparison data for requested suppliers
    """
    if supplier_names:
        filtered = [b for b in benchmarks if b.supplier_name in supplier_names]
    else:
        filtered = benchmarks[:10]  # Top 10 by default

    comparison = []
    for b in filtered:
        comparison.append(
            {
                "supplier_name": b.supplier_name,
                "rank": b.performance_rank,
                "tier": b.tier_classification,
                "efficiency": round(b.mean_normalized_efficiency, 2),
                "consistency": round(b.tool_consistency_score, 2),
                "total_tools": b.total_tools,
                "adjusted_score": round(b.adjusted_score, 2),
            }
        )

    return comparison
