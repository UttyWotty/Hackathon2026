"""
Duration Deviation Visualizations.

This module creates charts and visualizations for duration deviation analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import base64
import logging
from io import BytesIO
from typing import List, Optional

import matplotlib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import seaborn as sns  # type: ignore[import-untyped]

from ..models import CATEGORY_COLORS, DeviationMetrics

logger = logging.getLogger(__name__)

# Set default style
plt.style.use("seaborn-v0_8")
sns.set_palette("husl")


# ==================== Chart Generation ==================== #


def create_deviation_distribution_chart(
    metrics_list: List[DeviationMetrics],
) -> Optional[str]:
    """Create a chart showing duration deviation distribution.

    Args:
        metrics_list: List of deviation metrics

    Returns:
        str: Base64-encoded PNG image or None if creation fails
    """
    if not metrics_list:
        logger.warning("⚠️ No data for deviation distribution chart")
        return None

    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Deviation percentage histogram
        deviations = [m.deviation_percentage for m in metrics_list]
        ax1.hist(deviations, bins=20, alpha=0.7, color="skyblue", edgecolor="black")
        ax1.axvline(x=0, color="red", linestyle="--", alpha=0.7, label="Target")
        ax1.set_xlabel("Duration Deviation (%)")
        ax1.set_ylabel("Number of Equipment")
        ax1.set_title("Duration Deviation Distribution")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Category distribution pie chart
        categories = [m.deviation_category.value for m in metrics_list]
        category_counts = pd.Series(categories).value_counts()
        colors = [CATEGORY_COLORS.get(cat, "#95a5a6") for cat in category_counts.index]
        ax2.pie(
            category_counts.values,
            labels=category_counts.index,
            autopct="%1.1f%%",
            colors=colors,
        )
        ax2.set_title("Performance Category Distribution")

        plt.tight_layout()

        # Convert to base64
        img_data = _fig_to_base64(fig)
        plt.close(fig)

        logger.info("✅ Created deviation distribution chart")
        return img_data

    except Exception as e:
        logger.error(f"❌ Error creating deviation distribution chart: {e}")
        return None


def create_performance_comparison_chart(
    metrics_list: List[DeviationMetrics],
) -> Optional[str]:
    """Create a chart comparing equipment performance (efficiency vs stability).

    Args:
        metrics_list: List of deviation metrics

    Returns:
        str: Base64-encoded PNG image or None if creation fails
    """
    if not metrics_list:
        logger.warning("⚠️ No data for performance comparison chart")
        return None

    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Efficiency vs Stability scatter
        efficiencies = [m.efficiency_score for m in metrics_list]
        stabilities = [m.stability_score for m in metrics_list]
        machine_ids = [m.machine_id for m in metrics_list]

        ax1.scatter(efficiencies, stabilities, alpha=0.6, s=100, c="steelblue")
        ax1.set_xlabel("Efficiency Score (%)")
        ax1.set_ylabel("Stability Score (%)")
        ax1.set_title("Efficiency vs Stability")
        ax1.grid(True, alpha=0.3)

        # Highlight poor performers
        for i, code in enumerate(machine_ids):
            if efficiencies[i] < 70 or stabilities[i] < 70:
                ax1.annotate(
                    code,
                    (efficiencies[i], stabilities[i]),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                    color="red",
                )

        # Top 10 equipment by lowest absolute deviation
        top_10 = sorted(metrics_list, key=lambda x: abs(x.deviation_percentage))[:10]
        equipment_names = [m.machine_id for m in top_10]
        deviations = [abs(m.deviation_percentage) for m in top_10]

        bars = ax2.barh(equipment_names, deviations, color="lightgreen")
        ax2.set_xlabel("Absolute Duration Deviation (%)")
        ax2.set_title("Top 10 Best Performing Equipment")
        ax2.grid(True, alpha=0.3)

        # Add value labels
        for bar, dev in zip(bars, deviations):
            ax2.text(
                bar.get_width() + 0.1,
                bar.get_y() + bar.get_height() / 2,
                f"{dev:.1f}%",
                va="center",
                fontsize=8,
            )

        plt.tight_layout()

        # Convert to base64
        img_data = _fig_to_base64(fig)
        plt.close(fig)

        logger.info("✅ Created performance comparison chart")
        return img_data

    except Exception as e:
        logger.error(f"❌ Error creating performance comparison chart: {e}")
        return None


def create_time_series_chart(
    df: pd.DataFrame, machine_id: Optional[str] = None
) -> Optional[str]:
    """Create a time series chart showing CT over time for a specific equipment.

    Args:
        df: DataFrame with SHOT_TIME, duration, and TARGET_DURATION columns
        machine_id: Specific equipment to chart (uses most common if None)

    Returns:
        str: Base64-encoded PNG image or None if creation fails
    """
    if df.empty or "SHOT_TIME" not in df.columns:
        logger.warning("⚠️ No time series data available")
        return None

    try:
        # Select equipment
        if machine_id is None:
            machine_id = df["MACHINE_ID"].value_counts().index[0]

        sample_data = df[df["MACHINE_ID"] == machine_id].sort_values(
            "SHOT_TIME"
        )

        if sample_data.empty:
            logger.warning(f"⚠️ No data for equipment {machine_id}")
            return None

        fig, ax = plt.subplots(figsize=(15, 6))

        # Plot actual duration
        ax.plot(
            sample_data["SHOT_TIME"],
            sample_data["DURATION"],
            alpha=0.6,
            label="Actual Duration",
            linewidth=1,
            color="steelblue",
        )

        # Plot approved duration line
        if "TARGET_DURATION" in sample_data.columns:
            target_duration = sample_data["TARGET_DURATION"].iloc[0]
            ax.axhline(
                y=target_duration,
                color="red",
                linestyle="--",
                label="Approved Duration",
                alpha=0.8,
            )

        ax.set_xlabel("Time")
        ax.set_ylabel("Duration (seconds)")
        ax.set_title(f"CT Time Series - Equipment {machine_id}")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Rotate x-axis labels
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        plt.tight_layout()

        # Convert to base64
        img_data = _fig_to_base64(fig)
        plt.close(fig)

        logger.info(f"✅ Created time series chart for {machine_id}")
        return img_data

    except Exception as e:
        logger.error(f"❌ Error creating time series chart: {e}")
        return None


def create_supplier_comparison_chart(
    metrics_list: List[DeviationMetrics],
) -> Optional[str]:
    """Create a chart comparing performance across suppliers.

    Args:
        metrics_list: List of deviation metrics

    Returns:
        str: Base64-encoded PNG image or None if creation fails
    """
    if not metrics_list:
        logger.warning("⚠️ No data for supplier comparison chart")
        return None

    try:
        # Group by supplier
        supplier_data = {}
        for m in metrics_list:
            if m.vendor_name not in supplier_data:
                supplier_data[m.vendor_name] = {
                    "deviations": [],
                    "efficiencies": [],
                    "stabilities": [],
                }
            supplier_data[m.vendor_name]["deviations"].append(
                abs(m.deviation_percentage)
            )
            supplier_data[m.vendor_name]["efficiencies"].append(m.efficiency_score)
            supplier_data[m.vendor_name]["stabilities"].append(m.stability_score)

        # Calculate averages
        suppliers = list(supplier_data.keys())
        avg_deviations = [np.mean(supplier_data[s]["deviations"]) for s in suppliers]
        avg_efficiencies = [
            np.mean(supplier_data[s]["efficiencies"]) for s in suppliers
        ]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Average deviation by supplier
        ax1.barh(suppliers, avg_deviations, color="coral")
        ax1.set_xlabel("Average Absolute Deviation (%)")
        ax1.set_title("Average Duration Deviation by Supplier")
        ax1.grid(True, alpha=0.3)

        # Average efficiency by supplier
        ax2.barh(suppliers, avg_efficiencies, color="lightblue")
        ax2.set_xlabel("Average Efficiency Score (%)")
        ax2.set_title("Average Efficiency by Supplier")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        # Convert to base64
        img_data = _fig_to_base64(fig)
        plt.close(fig)

        logger.info("✅ Created supplier comparison chart")
        return img_data

    except Exception as e:
        logger.error(f"❌ Error creating supplier comparison chart: {e}")
        return None


# ==================== Helper Functions ==================== #


def _fig_to_base64(fig) -> str:
    """Convert a matplotlib figure to base64-encoded PNG.

    Args:
        fig: Matplotlib figure

    Returns:
        str: Base64-encoded PNG image
    """
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
    buffer.seek(0)
    img_data = base64.b64encode(buffer.read()).decode()
    buffer.close()
    return img_data
