"""
Tooling EOL API Wrapper.

This module provides a simplified API for running tooling end-of-life predictions,
designed for integration with LLM tools and external systems.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
from dotenv import load_dotenv

from .core import (
    create_snowpark_session,
    predict_end_of_life,
    read_shot_data,
    read_maintenance_events,
    read_tool_table,
)
from .models.config import get_utilization_bins
from .reporting import generate_html_report

# Load environment variables at module level (searches up directory tree automatically)
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


def run_analysis_api(
    output_dir: Optional[str] = None,
    save_csv: bool = True,
    save_html: bool = False,
    disable_maintenance: bool = False,
    type_category: Optional[str] = None,
) -> Dict[str, Any]:
    """Run EOL prediction end-to-end and return results.

    This is the main API entry point for tooling end-of-life prediction.
    It orchestrates data loading, prediction, and reporting.

    Args:
        output_dir: Directory to save output files (defaults to current directory)
        save_csv: If True, saves predictions as CSV
        save_html: If True, saves predictions as HTML
        disable_maintenance: If True, skips maintenance event integration
        type_category: Optional tooling family for family-specific bins

    Returns:
        Dict containing:
            - status: 'success' or 'error'
            - predictions: DataFrame with predictions (if successful)
            - output_files: Dict of generated file paths
            - message: Status message
            - error: Error message (if status is 'error')
    """
    try:
        # Setup output directory (centralized)
        if output_dir is None:
            from analysis.shared import get_output_dir

            output_dir = str(get_output_dir("tooling_eol"))
        else:
            os.makedirs(output_dir, exist_ok=True)

        # Connect to Snowflake
        logger.info("Connecting to Snowflake...")
        session = create_snowpark_session()

        # Read shot data
        logger.info("Reading SHOT_DATA...")
        df = read_shot_data(session)

        if df.empty:
            logger.warning("SHOT_DATA returned no rows.")
            return {
                "status": "error",
                "error": "No data found in SHOT_DATA",
                "predictions": pd.DataFrame(),
                "output_files": {},
                "message": "No data available for prediction",
            }

        # Enrich with TOOL reference
        try:
            logger.info("Enriching with TOOL table...")
            tool_ref = read_tool_table(session)
            if not tool_ref.empty and "TOOL_ID" in tool_ref.columns:
                df = df.merge(
                    tool_ref[
                        [
                            c
                            for c in [
                                "TOOL_ID",
                                "MACHINE_ID",
                                "DESIGNED_SHOT",
                                "MAX_DAILY_OUTPUT",
                                "PRODUCTION_DAYS",
                                "SHIFTS_PER_DAY",
                            ]
                            if c in tool_ref.columns
                        ]
                    ],
                    on="TOOL_ID",
                    how="left",
                    suffixes=("", "_MOLD"),
                )
                # Prefer MACHINE_ID from SHOT_DATA; keep merged column only if missing
                if (
                    "MACHINE_ID" not in df.columns
                    and "MACHINE_ID_MOLD" in df.columns
                ):
                    df = df.rename(columns={"MACHINE_ID_MOLD": "MACHINE_ID"})
        except Exception as exc:
            logger.warning(f"MOLD enrichment skipped due to error: {exc}")

        # Optional maintenance events
        maintenance_events = None
        if (
            not disable_maintenance
            and os.getenv("DISABLE_MAINTENANCE", "false").lower() != "true"
        ):
            try:
                logger.info("Loading maintenance events...")
                maintenance_events = read_maintenance_events(session)
                if maintenance_events is not None and not maintenance_events.empty:
                    logger.info(
                        f"Loaded maintenance events: {len(maintenance_events)} rows, "
                        f"{maintenance_events['TOOL_ID'].nunique()} molds"
                    )
                else:
                    logger.info(
                        "No maintenance events found; running without adjustments"
                    )
            except Exception as exc:
                logger.warning(f"Maintenance events read failed: {exc}")
        else:
            logger.info("Maintenance integration disabled")

        # Get utilization bins based on tooling family
        bins = get_utilization_bins(type_category)

        # Run predictions
        num_molds = df["TOOL_ID"].nunique()
        logger.info(f"Running predictions for {num_molds} molds...")
        predictions = predict_end_of_life(
            df, bins=bins, maintenance_events=maintenance_events
        )
        logger.info(f"Generated predictions: {len(predictions)} rows")

        # Safety fallback: if maintenance caused empty output, rerun without it
        if (
            predictions is None or len(predictions) == 0
        ) and maintenance_events is not None:
            logger.warning(
                "Predictions empty with maintenance enabled; rerunning without maintenance events"
            )
            predictions = predict_end_of_life(df, bins=bins, maintenance_events=None)
            logger.info(f"Generated predictions (fallback): {len(predictions)} rows")

        output_files = {}

        # Save CSV
        if save_csv:
            csv_path = os.path.join(output_dir, "tooling_eol_predictions.csv")
            predictions.to_csv(csv_path, index=False)
            output_files["csv"] = csv_path
            logger.info(f"Saved predictions to {csv_path}")

        # Save HTML
        if save_html:
            html_path = os.path.join(output_dir, "tooling_eol_predictions.html")
            generate_html_report(predictions, output_path=html_path)
            output_files["html"] = html_path

        return {
            "status": "success",
            "predictions": predictions,
            "output_files": output_files,
            "message": f"Successfully generated predictions for {len(predictions)} molds",
            "num_molds": len(predictions),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as exc:
        logger.error(f"Error during EOL prediction: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "predictions": pd.DataFrame(),
            "output_files": {},
            "message": f"Prediction failed: {exc}",
        }


# Maintain backwards compatibility with the original interface
def main(save_csv: bool = True, save_html: bool = False) -> pd.DataFrame:
    """Run EOL prediction end-to-end and optionally write to CSV.

    This function maintains backwards compatibility with the original predictor.py interface.

    Args:
        save_csv: If True, writes output CSV
        save_html: If True, writes output HTML

    Returns:
        pd.DataFrame: Predictions dataframe
    """
    result = run_analysis_api(save_csv=save_csv, save_html=save_html)
    if result["status"] == "error":
        logger.error(f"Prediction failed: {result['error']}")
        return pd.DataFrame()
    return result["predictions"]
