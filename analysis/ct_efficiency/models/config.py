"""
CT Efficiency Models and Configuration.

This module contains data models and configuration for cycle time efficiency
analysis and supplier benchmarking.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

# ==================== Data Models ==================== #


@dataclass
class DataQualityIssue:
    """Data class for tracking data quality issues.

    Attributes:
        issue_type: Type of quality issue (e.g., 'missing_data', 'outlier')
        description: Human-readable description of the issue
        affected_records: Number of records affected
        severity: Issue severity level ('low', 'medium', 'high', 'critical')
    """

    issue_type: str
    description: str
    affected_records: int
    severity: str  # 'low', 'medium', 'high', 'critical'


@dataclass
class EfficiencyMetrics:
    """Data class for efficiency metrics with confidence intervals.

    Attributes:
        efficiency: Calculated efficiency percentage
        confidence_interval_lower: Lower bound of confidence interval
        confidence_interval_upper: Upper bound of confidence interval
        sample_size: Number of samples used in calculation
        standard_error: Standard error of the efficiency estimate
    """

    efficiency: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    sample_size: int
    standard_error: float


@dataclass
class SupplierBenchmark:
    """Data class for supplier benchmarking results.

    Attributes:
        supplier_id: Unique supplier identifier
        supplier_name: Supplier name
        mean_normalized_efficiency: Normalized efficiency score (0-100)
        tool_consistency_score: Consistency across tools (0-100)
        total_tools: Number of tools analyzed for this supplier
        performance_rank: Rank among all suppliers (1 = best)
        tier_classification: Performance tier (Excellent/Good/Average/Needs Improvement)
        adjusted_score: Score adjusted for tool count (default: 0.0)
    """

    supplier_id: str
    supplier_name: str
    mean_normalized_efficiency: float
    tool_consistency_score: float
    total_tools: int
    performance_rank: int
    tier_classification: str
    adjusted_score: float = 0.0


@dataclass
class OperatorShiftPattern:
    """Detected shift pattern for a single equipment.

    Attributes:
        equipment_code: Machine identifier
        tooling_type: Tooling type classification
        total_sessions: Number of production sessions detected
        avg_session_duration_hours: Average active production session length
        avg_break_duration_hours: Average intra-production break length (<=8h)
        production_end_count: Number of long breaks (>8h) indicating end of production
        has_planned_downtime: Whether consistent break patterns suggest planned downtime
        runs_nonstop: Whether machine shows no significant breaks within sessions
        avg_warmup_penalty_pct: Efficiency drop in first shots after production end
        shots_per_session: Average shots per production session
    """

    equipment_code: str
    tooling_type: str
    total_sessions: int
    avg_session_duration_hours: float
    avg_break_duration_hours: float
    production_end_count: int
    has_planned_downtime: bool
    runs_nonstop: bool
    avg_warmup_penalty_pct: float
    shots_per_session: float
    break_schedule: List[Dict[str, object]]  # Detected recurring break windows


@dataclass
class OperatorBenchmark:
    """Benchmarking result for operator-level analysis per equipment.

    Attributes:
        equipment_code: Machine identifier
        tooling_type: Tooling type classification
        supplier_name: Supplier name for context
        session_count: Number of production sessions analyzed
        mean_efficiency_pct: Mean efficiency across all sessions
        within_session_consistency: Consistency within a single session (0-100)
        cross_session_consistency: Consistency across sessions (0-100)
        warmup_impact_pct: Average efficiency loss in first N shots after >8h break
        performance_rank: Rank among equipment (1 = best)
        tier_classification: Performance tier label
        adjusted_score: Weighted score for ranking
    """

    equipment_code: str
    tooling_type: str
    supplier_name: str
    session_count: int
    mean_efficiency_pct: float
    within_session_consistency: float
    cross_session_consistency: float
    warmup_impact_pct: float
    performance_rank: int
    tier_classification: str
    adjusted_score: float = 0.0


# ==================== Configuration ==================== #


def get_default_config() -> Dict:
    """Get default configuration parameters for CT efficiency analysis.

    Returns:
        Dict: Configuration dictionary with all analysis parameters
    """
    return {
        "anomaly_detection": {
            "z_score_threshold": 2.0,
            "iqr_multiplier": 1.5,
            "isolation_forest_contamination": 0.1,
        },
        "statistical_tiers": {
            "excellent_threshold": 1.5,  # z-score
            "good_threshold": 0.5,
            "average_threshold": -0.5,
            "needs_improvement_threshold": -1.5,
        },
        "confidence_level": 0.95,
        "trend_analysis": {"min_data_points": 10, "forecast_periods": 6},
        "benchmarking": {
            "industry_standards": {
                "excellent_efficiency": 15.0,  # %
                "good_efficiency": 10.0,
                "average_efficiency": 5.0,
                "poor_efficiency": 0.0,
            },
            "normalization_methods": ["z_score", "min_max", "percentile"],
            "supplier_tier_thresholds": {
                "excellent": 0.8,  # 80th percentile
                "good": 0.6,  # 60th percentile
                "average": 0.4,  # 40th percentile
                "needs_improvement": 0.2,  # 20th percentile
            },
        },
    }


# ==================== Constants ==================== #


# Severity levels for quality issues
SEVERITY_LEVELS = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# Tier classification labels
TIER_EXCELLENT = "Excellent"
TIER_GOOD = "Good"
TIER_AVERAGE = "Average"
TIER_NEEDS_IMPROVEMENT = "Needs Improvement"
TIER_POOR = "Poor"

# Supplier tier classifications
TIER_CLASSIFICATIONS = [
    TIER_EXCELLENT,
    TIER_GOOD,
    TIER_AVERAGE,
    TIER_NEEDS_IMPROVEMENT,
    TIER_POOR,
]

# Color schemes for visualizations
TIER_COLORS = {
    TIER_EXCELLENT: "#2ecc71",  # Green
    TIER_GOOD: "#3498db",  # Blue
    TIER_AVERAGE: "#f39c12",  # Orange
    TIER_NEEDS_IMPROVEMENT: "#e67e22",  # Dark orange
    TIER_POOR: "#e74c3c",  # Red
}

# Statistical thresholds
Z_SCORE_THRESHOLD = 2.0
IQR_MULTIPLIER = 1.5
CONFIDENCE_LEVEL = 0.95

# Minimum data points for reliable analysis
MIN_SAMPLE_SIZE = 30
MIN_TOOLS_FOR_CONSISTENCY = 3

# Operator benchmarking constants
PRODUCTION_END_BREAK_HOURS = 8.0  # Breaks longer than this = end of production
WARMUP_SHOT_COUNT = 20  # Number of initial shots to measure warmup penalty
PLANNED_DOWNTIME_CV_THRESHOLD = 0.3  # CV of break start times below this = planned
MIN_SESSIONS_FOR_ANALYSIS = 3  # Minimum valid sessions for break clustering
MIN_SESSIONS_FOR_SHIFT_REPORT = 10  # Minimum sessions to include in shift report
MIN_SHOTS_PER_SESSION = 100  # Sessions with fewer shots are discarded
PLANNED_DOWNTIME_MIN_RATIO = 0.5  # Pattern must appear in >= 50% of sessions
BREAK_CLUSTER_WINDOW_HOURS = 1.0  # Hour window for grouping break times into clusters


# ==================== Helper Functions ==================== #


def classify_supplier_tier(normalized_score: float, thresholds: Dict = None) -> str:
    """Classify supplier into performance tier based on normalized score.

    Args:
        normalized_score: Normalized efficiency score (0-1 scale)
        thresholds: Optional custom thresholds dict

    Returns:
        str: Tier classification string
    """
    if thresholds is None:
        thresholds = get_default_config()["benchmarking"]["supplier_tier_thresholds"]

    if normalized_score >= thresholds["excellent"]:
        return TIER_EXCELLENT
    elif normalized_score >= thresholds["good"]:
        return TIER_GOOD
    elif normalized_score >= thresholds["average"]:
        return TIER_AVERAGE
    elif normalized_score >= thresholds["needs_improvement"]:
        return TIER_NEEDS_IMPROVEMENT
    else:
        return TIER_POOR


def get_severity_weight(severity: str) -> int:
    """Get numeric weight for quality issue severity.

    Args:
        severity: Severity level string

    Returns:
        int: Numeric weight (1-4, higher = more severe)
    """
    return SEVERITY_LEVELS.get(severity.lower(), 1)


def get_tier_color(tier: str) -> str:
    """Get color code for a performance tier.

    Args:
        tier: Tier classification string

    Returns:
        str: Hex color code
    """
    return TIER_COLORS.get(tier, "#95a5a6")  # Default gray
