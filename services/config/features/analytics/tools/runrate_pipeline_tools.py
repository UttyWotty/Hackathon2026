"""Run Rate pipeline tool wrapper for the scheduler/dispatcher.

Wraps services.config.features.analytics.pipelines.run_rate.main.run so the
scheduler's tool dispatcher receives the standard {"status", ...} dict shape.
The underlying pipeline function returns a bare bool, which the dispatcher
cannot interpret directly.
"""

import logging
from typing import Any, Dict, Optional

from services.config.features.analytics.pipelines.run_rate.main import (
    run as _run_run_rate,
)

logger = logging.getLogger(__name__)

DEFAULT_OVERLAP_DAYS: int = 7
DEFAULT_FULL_HISTORICAL_LOAD: bool = False


def refresh_run_rate_pipeline(
    schema_name: Optional[str] = None,
    full_historical_load: bool = DEFAULT_FULL_HISTORICAL_LOAD,
    overlap_days: int = DEFAULT_OVERLAP_DAYS,
) -> Dict[str, Any]:
    """Run the run_rate pipeline for a single schema.

    Args:
        schema_name: Snowflake schema (client) to refresh, e.g. "VANTIS", "NORDPLAST".
        full_historical_load: When True, reprocess all history. Defaults to False.
        overlap_days: Days to reprocess in incremental mode. Defaults to 7.

    Returns:
        Dispatcher-compatible dict with status/schema/result fields.
    """
    logger.info(
        "Scheduled run_rate pipeline starting: schema=%s, full=%s, overlap=%d",
        schema_name,
        full_historical_load,
        overlap_days,
    )
    try:
        success = _run_run_rate(
            full_historical_load=full_historical_load,
            overlap_days=overlap_days,
            schema_name=schema_name,
        )
        if success:
            logger.info("run_rate pipeline succeeded for schema=%s", schema_name)
            return {
                "status": "success",
                "schema": schema_name,
                "full_historical_load": full_historical_load,
                "overlap_days": overlap_days,
            }
        logger.error("run_rate pipeline returned False for schema=%s", schema_name)
        return {
            "status": "error",
            "schema": schema_name,
            "error": "Pipeline returned False",
        }
    except Exception as exc:
        logger.error(
            "run_rate pipeline raised for schema=%s: %s",
            schema_name,
            exc,
            exc_info=True,
        )
        return {
            "status": "error",
            "schema": schema_name,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
