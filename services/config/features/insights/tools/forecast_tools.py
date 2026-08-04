"""Production metric forecasting tool adapter.

Builds a daily history series from DEMO_TABLE for shot volume or average cycle
time and extrapolates it with the trend/moving-average logic in analysis.insights.
Exposes the forecast_metric MCP tool.
"""

import logging
from typing import Any, Dict, Optional

from analysis.insights.forecasting import forecast_values, summarize_forecast
from services.config.features.insights.tools.common import (
    InvalidToolParameterError,
    positive_int,
    query_records,
    safe_param,
)

logger = logging.getLogger(__name__)

MAX_HISTORY_DAYS: int = 365
DEFAULT_HISTORY_DAYS: int = 60
MAX_HORIZON_DAYS: int = 60
DEFAULT_HORIZON_DAYS: int = 14
HARD_STOP_CT: float = 999.0

METRIC_DAILY_SHOTS: str = "daily_shots"
METRIC_DAILY_AVG_CT: str = "daily_avg_ct"
SUPPORTED_METRICS: tuple = (METRIC_DAILY_SHOTS, METRIC_DAILY_AVG_CT)

METRIC_EXPRESSIONS: Dict[str, str] = {
    METRIC_DAILY_SHOTS: "COUNT(*)",
    METRIC_DAILY_AVG_CT: "AVG(CASE WHEN CT < %s THEN CT END)" % HARD_STOP_CT,
}


def forecast_metric(
    metric: str = METRIC_DAILY_SHOTS,
    equipment_code: Optional[str] = None,
    history_days: int = DEFAULT_HISTORY_DAYS,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> Dict[str, Any]:
    """Forecast a daily production metric from its recent history.

    Args:
        metric: daily_shots or daily_avg_ct (default: daily_shots).
        equipment_code: Optional single-equipment filter (plant-wide when omitted).
        history_days: History window in days (default: 60, max: 365).
        horizon_days: Days to forecast (default: 14, max: 60).

    Returns:
        dict with the historical series, the forecast, the method used, and a
        forecast-vs-history summary.
    """
    try:
        if metric not in SUPPORTED_METRICS:
            raise InvalidToolParameterError(
                "Unsupported metric: %s (use one of %s)"
                % (metric, ", ".join(SUPPORTED_METRICS))
            )
        history_days = positive_int(history_days, "history_days", MAX_HISTORY_DAYS)
        horizon_days = positive_int(horizon_days, "horizon_days", MAX_HORIZON_DAYS)

        equipment_filter = ""
        if equipment_code:
            equipment_filter = "AND EQUIPMENT_CODE = '%s'" % safe_param(
                equipment_code, "equipment_code"
            )

        rows = query_records(f"""
            SELECT DATE(LOCAL_SHOT_TIME) AS DAY,
                   {METRIC_EXPRESSIONS[metric]} AS VALUE
            FROM DEMO_TABLE
            WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{history_days}, CURRENT_DATE())
              AND EQUIPMENT_CODE IS NOT NULL
              {equipment_filter}
            GROUP BY DATE(LOCAL_SHOT_TIME)
            ORDER BY DAY
            """)
        history = [
            {"day": r["DAY"], "value": round(float(r["VALUE"]), 2)}
            for r in rows
            if r.get("VALUE") is not None
        ]
        if not history:
            return {
                "status": "error",
                "error": "No history found for the requested window",
            }

        values = [point["value"] for point in history]
        forecast = forecast_values(values, horizon_days)
        summary = summarize_forecast(forecast["forecast"], forecast["history_mean"])

        return {
            "status": "success",
            "metric": metric,
            "equipment_code": equipment_code,
            "history_days": history_days,
            "horizon_days": horizon_days,
            "active_history_days": len(history),
            "history": history,
            **forecast,
            **summary,
            "notes": "History uses active production days only; idle days are not zero-filled.",
        }
    except Exception as e:
        logger.error("forecast_metric failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
