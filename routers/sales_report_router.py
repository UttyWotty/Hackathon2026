"""
Sales Report Router - SQUAD presentation generation endpoint.
Exposes a single POST endpoint that accepts client configuration,
runs all required analyses, and generates a downloadable PPT file.
"""

import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.sales_report.config import (
    BusinessRecommendation,
    SalesReportConfig,
    ToolConfig,
)
from services.sales_report.data_aggregator import aggregate_all_data
from services.sales_report.ppt_builder import build_squad_presentation
from services.sales_report.tool_metadata_fetcher import fetch_tool_metadata
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()

# -- Auth setup (mirrors analytics_router pattern) --
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "False").lower() == "true"


def _noop_decorator(func):
    """No-op decorator used when authentication is disabled or unavailable."""
    return func


if AUTH_ENABLED:
    try:
        from services.infrastructure.auth.decorators import require_auth

        auth_decorator = require_auth
    except ImportError:
        auth_decorator = _noop_decorator
else:
    auth_decorator = _noop_decorator


# ============================================================================
# Request Models
# ============================================================================


class ToolConfigRequest(BaseModel):
    """Single tool configuration in the report request."""

    equipment_code: str = Field(
        ..., description="Equipment code from master_shot_table"
    )
    part_cost: Optional[float] = Field(
        None,
        description="Override part cost in dollars. "
        "If not provided, defaults to $0.50 (Injection) or $5.00 (Stamping)",
    )


class RecommendationsRequest(BaseModel):
    """Business recommendations input from sales team."""

    ask_amount: float = Field(0.0, description="Budget ask in dollars")
    supplier_count: int = Field(0, description="Number of critical suppliers")
    tool_count: int = Field(0, description="Total number of tools")
    tools_per_supplier: int = Field(100, description="Average tools per supplier site")
    expected_saving: float = Field(0.0, description="Expected saving opportunity")
    notes: List[str] = Field(
        default_factory=list, description="Additional notes for the slide"
    )


class SalesReportRequest(BaseModel):
    """
    Full request to generate a SQUAD sales presentation.

    Only equipment_codes are required per tool. Commodity, cavities,
    and contracted cycle time are fetched automatically from
    master_shot_table (approved_ct, tooling_type, volume columns).
    """

    client_name: str = Field(..., description="Client company name (e.g. VANTIS)")
    client_folder: str = Field(
        ...,
        description="Folder name under assets/clients/ for logos and images "
        "(e.g. 'vantis' maps to assets/clients/vantis/)",
    )
    presentation_title: str = Field(
        "SQUAD Presentation", description="Title on cover slide"
    )
    start_date: str = Field(..., description="Analysis start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Analysis end date (YYYY-MM-DD)")
    equipment_codes: List[str] = Field(
        ...,
        description="Equipment codes to include in the report. "
        "Metadata (commodity, cavities, approved_ct) is fetched from "
        "master_shot_table automatically.",
    )
    part_cost_overrides: Dict[str, float] = Field(
        default_factory=dict,
        description="Optional per-tool part cost overrides. "
        "Key = equipment_code, value = cost in dollars. "
        "Example: {'EMA-4101': 0.5, '3BD3008371': 5.0}",
    )
    machine_rate_per_hour: float = Field(170.0, description="Machine rate $/hour")
    labor_cost_per_hour: float = Field(10.0, description="Labor cost $/hour")
    project_cost: float = Field(
        11709.0, description="Total project cost for ROI calculation"
    )
    recommendations: Optional[RecommendationsRequest] = Field(
        None, description="Business recommendations (optional)"
    )
    screenshot_paths: Dict[str, str] = Field(
        default_factory=dict,
        description="Optional screenshot image paths. "
        "Keys: 'deep_dive_{equipment_code}' for page-7 style screenshots, "
        "'runrate_chart_{equipment_code}' for run rate chart screenshots. "
        "Leave empty for placeholder boxes.",
    )


# ============================================================================
# Endpoint
# ============================================================================


@router.post("/generate")
@auth_decorator
async def generate_sales_report(request: SalesReportRequest):
    """
    Generate a SQUAD sales presentation for a client.

    Fetches tool metadata (commodity, cavities, approved_ct) from
    master_shot_table, runs ROI/RunRate/Capacity analyses, then
    assembles a branded PowerPoint file.

    Returns the file path and download URL on success.
    """
    logger.info(
        "Generating sales report for %s with %d tools",
        request.client_name,
        len(request.equipment_codes),
    )

    try:
        # Fetch tool metadata from Snowflake
        metadata = await fetch_tool_metadata(
            request.equipment_codes, client=request.client_name
        )

        config = _build_config(request, metadata)
        aggregated_data = await aggregate_all_data(config)
        ppt_path = build_squad_presentation(config, aggregated_data)

        return {
            "status": "success",
            "message": (f"SQUAD presentation generated for {request.client_name}"),
            "ppt_path": ppt_path,
            "tools_included": len(request.equipment_codes),
            "tools_metadata_found": len(metadata),
            "download_url": (f"/sales-reports/download/{os.path.basename(ppt_path)}"),
        }

    except Exception as exc:
        logger.error("Sales report generation failed: %s", exc)
        safe_msg = sanitize_error_message(str(exc))
        raise HTTPException(status_code=500, detail=safe_msg) from exc


@router.get("/download/{filename}")
async def download_report(filename: str):
    """
    Download a generated sales report PPT file.

    Args:
        filename: Name of the generated .pptx file.
    """
    file_path = os.path.join("output/sales_reports", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".presentationml.presentation"
        ),
    )


@router.get("/clients")
async def list_client_assets():
    """
    List available client asset directories.

    Returns client folder names that have an assets/clients/<folder>/ directory.
    """
    assets_dir = "assets/clients"
    if not os.path.isdir(assets_dir):
        return {"clients": []}
    clients = [
        d for d in os.listdir(assets_dir) if os.path.isdir(os.path.join(assets_dir, d))
    ]
    return {"clients": sorted(clients)}


# ============================================================================
# Helpers
# ============================================================================


def _build_config(
    request: SalesReportRequest,
    metadata: Dict[str, Dict],
) -> SalesReportConfig:
    """
    Convert API request + Snowflake metadata into SalesReportConfig.

    Merges auto-fetched metadata (commodity, cavities, approved_ct) with
    any user-provided part_cost overrides.

    Args:
        request: Validated API request.
        metadata: Per-equipment metadata from master_shot_table.

    Returns:
        SalesReportConfig ready for the PPT builder.
    """
    tools: List[ToolConfig] = []
    for code in request.equipment_codes:
        meta = metadata.get(code, {})
        part_cost_override = request.part_cost_overrides.get(code)

        tools.append(
            ToolConfig(
                equipment_code=code,
                commodity=meta.get("commodity", "Injection"),
                part_cost=part_cost_override,
                cavities=meta.get("cavities"),
                contracted_ct_seconds=meta.get("approved_ct"),
            )
        )

    recs = None
    if request.recommendations:
        r = request.recommendations
        recs = BusinessRecommendation(
            ask_amount=r.ask_amount,
            supplier_count=r.supplier_count,
            tool_count=r.tool_count,
            tools_per_supplier=r.tools_per_supplier,
            expected_saving=r.expected_saving,
            notes=r.notes,
        )

    return SalesReportConfig(
        client_name=request.client_name,
        client_slug=request.client_folder,
        presentation_title=request.presentation_title,
        start_date=request.start_date,
        end_date=request.end_date,
        tools=tools,
        machine_rate_per_hour=request.machine_rate_per_hour,
        labor_cost_per_hour=request.labor_cost_per_hour,
        project_cost=request.project_cost,
        recommendations=recs,
        screenshot_paths=request.screenshot_paths,
    )
