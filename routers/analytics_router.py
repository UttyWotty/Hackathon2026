"""
Analytics Router - All manufacturing analysis endpoints.

This router provides access to all analysis tools:
- ROI Analysis
- RunRate Analysis
- RCA (Root Cause Analysis)
- CT Efficiency
- CT Deviation
- Tooling EOL
- Capacity Planning

Each endpoint directly calls the analysis modules in the analysis/ folder.
No HTTP overhead, no microservices complexity - just clean, direct function calls.

Security:
- Input validation to prevent SQL injection
- Optional authentication (if AUTH_ENABLED=True)
"""

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.config.features.analytics.tools.capacity_tools import (
    run_capacity_analysis,
)
from services.config.features.analytics.tools.ct_deviation_tools import (
    run_ct_deviation_analysis,
)
from services.config.features.analytics.tools.ct_efficiency_tools import (
    run_ct_efficiency_analysis,
)
from services.config.features.analytics.tools.rca_tools import run_rca_analysis

# Import actual analysis tools
from services.config.features.analytics.tools.roi_tools import run_roi_analysis
from services.config.features.analytics.tools.runrate_tools import run_runrate_analysis
from services.config.features.analytics.tools.tooling_eol_tools import (
    run_tooling_eol_analysis,
)
from utils.error_handling import sanitize_error_message

# Import security utilities
from utils.input_validation import InputValidationError, validate_analytics_request

logger = logging.getLogger(__name__)

# Check if auth is enabled
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "False").lower() == "true"


def _noop_decorator(func):
    """No-op decorator used when authentication is disabled or unavailable."""
    return func


# Import auth decorator if enabled
if AUTH_ENABLED:
    try:
        from services.infrastructure.auth.decorators import require_auth

        auth_decorator = require_auth
        logger.info("✅ Authentication enabled for analytics endpoints")
    except ImportError:
        logger.warning(
            "⚠️  Auth enabled but decorator not available - endpoints will be unprotected"
        )
        auth_decorator = _noop_decorator
else:
    auth_decorator = _noop_decorator
    logger.info("ℹ️  Authentication disabled for analytics endpoints")

# Create router
router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class ROIAnalysisRequest(BaseModel):
    """ROI Analysis request parameters"""

    equipment_codes: List[str] = Field(
        ..., description="List of equipment codes to analyze"
    )
    supplier_names: Optional[List[str]] = Field(
        None, description="Optional supplier filter"
    )
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    delta_tolerance: float = Field(
        0.05, description="Delta tolerance for suspicious records"
    )
    client: str = Field("VANTIS", description="Client name")
    aggregation_level: str = Field(
        "daily", description="Aggregation level: daily, weekly, monthly"
    )


class RunRateAnalysisRequest(BaseModel):
    """RunRate Analysis request parameters"""

    equipment_codes: List[str] = Field(..., description="Equipment codes to analyze")
    supplier_names: Optional[List[str]] = Field(
        None, description="Optional supplier filter"
    )
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    client: str = Field("VANTIS", description="Client name")


class RCAAnalysisRequest(BaseModel):
    """Root Cause Analysis request parameters"""

    equipment_codes: List[str] = Field(..., description="Equipment codes to analyze")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    client: str = Field("VANTIS", description="Client name")


class CTEfficiencyRequest(BaseModel):
    """CT Efficiency Analysis request parameters"""

    equipment_codes: List[str] = Field(
        default_factory=list, description="Equipment codes to analyze (empty = all)"
    )
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    client: str = Field("VANTIS", description="Client name")


class CTDeviationRequest(BaseModel):
    """CT Deviation Analysis request parameters"""

    equipment_codes: List[str] = Field(..., description="Equipment codes to analyze")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    client: str = Field("VANTIS", description="Client name")


class ToolingEOLRequest(BaseModel):
    """Tooling EOL Analysis request parameters"""

    equipment_codes: List[str] = Field(..., description="Equipment codes to analyze")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    client: str = Field("VANTIS", description="Client name")


class CapacityRequest(BaseModel):
    """Capacity Planning request parameters"""

    equipment_codes: List[str] = Field(..., description="Equipment codes to analyze")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    client: str = Field("VANTIS", description="Client name")


# ============================================================================
# Analytics Endpoints
# ============================================================================


@router.get("/")
async def analytics_info():
    """Get information about available analytics tools"""
    return {
        "service": "Manufacturing Analytics",
        "description": "All manufacturing analysis tools in one place",
        "available_tools": [
            "ROI Analysis - Return on Investment analysis",
            "RunRate Analysis - Production run rate and efficiency",
            "RCA - Root Cause Analysis for issues",
            "CT Efficiency - Cycle time efficiency analysis",
            "CT Deviation - Cycle time deviation detection",
            "Tooling EOL - End of life prediction",
            "Capacity Planning - Production capacity analysis",
        ],
        "endpoints": {
            "roi": "POST /analytics/roi",
            "runrate": "POST /analytics/runrate",
            "rca": "POST /analytics/rca",
            "ct_efficiency": "POST /analytics/ct-efficiency",
            "ct_deviation": "POST /analytics/ct-deviation",
            "tooling_eol": "POST /analytics/tooling-eol",
            "capacity": "POST /analytics/capacity",
        },
        "pipelines": "See /pipelines for data pipeline operations",
    }


@router.post("/roi")
@auth_decorator
async def roi_analysis(request: ROIAnalysisRequest):
    """
    Run ROI (Return on Investment) Analysis.

    Analyzes manufacturing data to identify suspicious records and calculate ROI metrics.
    Generates Excel report with detailed analysis.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS",
      "aggregation_level": "daily"
    }
    ```
    """
    logger.info(f"ROI analysis requested for equipment: {request.equipment_codes}")

    try:
        # Validate and sanitize inputs
        validated = validate_analytics_request(
            equipment_codes=request.equipment_codes,
            supplier_names=request.supplier_names,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        result = await run_roi_analysis(
            equipment_codes=validated["equipment_codes"],
            supplier_names=validated.get("supplier_names"),
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            delta_tolerance=request.delta_tolerance,
            client=request.client,
            aggregation_level=request.aggregation_level,
        )
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for ROI analysis: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"ROI analysis failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "ROI analysis failed. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/runrate")
@auth_decorator
async def runrate_analysis(request: RunRateAnalysisRequest):
    """
    Run RunRate Analysis.

    Analyzes production run rates, efficiency, stops, and downtime.
    Generates Excel report with session-level analysis.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS"
    }
    ```
    """
    logger.info(f"RunRate analysis requested for equipment: {request.equipment_codes}")

    try:
        # Validate and sanitize inputs
        validated = validate_analytics_request(
            equipment_codes=request.equipment_codes,
            supplier_names=request.supplier_names,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        result = await run_runrate_analysis(
            equipment_codes=validated["equipment_codes"],
            supplier_names=validated.get("supplier_names"),
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            client=request.client,
        )
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for RunRate analysis: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"RunRate analysis failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "RunRate analysis failed. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/rca")
@auth_decorator
async def rca_analysis(request: RCAAnalysisRequest):
    """
    Run Root Cause Analysis (RCA).

    Identifies root causes of production issues using master shot table.
    Generates comprehensive analysis report.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS"
    }
    ```
    """
    logger.info(f"RCA requested for equipment: {request.equipment_codes}")

    try:
        # Validate and sanitize inputs
        validated = validate_analytics_request(
            equipment_codes=request.equipment_codes,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        # run_rca_analysis is schema-aware via snowflake_schema and does not take
        # a date range; pass the client through as the schema override.
        result = await run_rca_analysis(
            equipment_codes=validated["equipment_codes"],
            snowflake_schema=request.client,
        )
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for RCA: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"RCA failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "RCA analysis failed. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/ct-efficiency")
@auth_decorator
async def ct_efficiency_analysis(request: CTEfficiencyRequest):
    """
    Run Cycle Time Efficiency Analysis.

    Analyzes cycle time efficiency and identifies improvement opportunities.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS"
    }
    ```
    """
    logger.info(
        f"CT Efficiency analysis requested for equipment: {request.equipment_codes}"
    )

    try:
        # Validate and sanitize inputs
        validated = validate_analytics_request(
            equipment_codes=request.equipment_codes or None,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        result = run_ct_efficiency_analysis(
            equipment_codes=validated.get("equipment_codes"),
            start_date=validated.get("start_date"),
            end_date=validated.get("end_date"),
            client=request.client,
        )
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for CT Efficiency: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"CT Efficiency analysis failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "CT Efficiency analysis failed. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/ct-deviation")
@auth_decorator
async def ct_deviation_analysis(request: CTDeviationRequest):
    """
    Run Cycle Time Deviation Analysis.

    Detects cycle time deviations and anomalies.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS"
    }
    ```
    """
    logger.info(
        f"CT Deviation analysis requested for equipment: {request.equipment_codes}"
    )

    try:
        # Validate and sanitize inputs
        validated = validate_analytics_request(
            equipment_codes=request.equipment_codes,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        # run_ct_deviation_analysis has no schema parameter; it uses the default
        # schema from .env and filters by equipment/supplier only.
        result = run_ct_deviation_analysis(
            equipment_codes=validated["equipment_codes"],
            start_date=validated["start_date"],
            end_date=validated["end_date"],
        )
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for CT Deviation: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"CT Deviation analysis failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "CT Deviation analysis failed. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/tooling-eol")
@auth_decorator
async def tooling_eol_analysis(request: ToolingEOLRequest):
    """
    Run Tooling End-of-Life Analysis.

    Predicts when tooling will reach end of life based on usage patterns.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS"
    }
    ```
    """
    logger.info(
        f"Tooling EOL analysis requested for equipment: {request.equipment_codes}"
    )

    try:
        # Validate inputs for a consistent 400 on bad input. run_tooling_eol_analysis
        # analyzes all molds and takes none of the request's equipment/date/client
        # filters, so the validated values are intentionally not forwarded.
        validate_analytics_request(
            equipment_codes=request.equipment_codes,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        result = await run_tooling_eol_analysis()
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for Tooling EOL: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Tooling EOL analysis failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Tooling EOL analysis failed. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/capacity")
@auth_decorator
async def capacity_planning(request: CapacityRequest):
    """
    Run Capacity Planning Analysis.

    Analyzes production capacity and identifies bottlenecks.

    **Example:**
    ```json
    {
      "equipment_codes": ["EMA-4101"],
      "start_date": "2025-11-01",
      "end_date": "2025-11-30",
      "client": "VANTIS"
    }
    ```
    """
    logger.info(f"Capacity planning requested for equipment: {request.equipment_codes}")

    try:
        # Validate and sanitize inputs
        validated = validate_analytics_request(
            equipment_codes=request.equipment_codes,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        result = await run_capacity_analysis(
            equipment_codes=validated["equipment_codes"],
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            client=request.client,
        )
        return result
    except InputValidationError as e:
        logger.warning(f"Input validation failed for Capacity Planning: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Capacity planning failed: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e,
            "Capacity planning analysis failed. Please check your input and try again.",
        )
        raise HTTPException(status_code=500, detail=error_msg)
