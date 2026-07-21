"""PowerPoint Generation Tools for MCP Protocol
============================================

Provides LLM-accessible tools for generating PowerPoint presentations
from analysis results.

Author: Utku Gulbardak
Date: 2025-11-28
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


async def generate_presentation(
    analysis_type: str,
    metrics: Dict[str, Any],
    session_data: Optional[List[Dict]] = None,
    equipment_code: Optional[str] = None,
    supplier_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate PowerPoint presentation from analysis results.

    Creates a professional PowerPoint with executive summary, key metrics,
    charts, and recommendations based on analysis type.

    Args:
        analysis_type: Type of analysis (runrate, roi, capacity, etc.)
        metrics: Analysis metrics dictionary
        session_data: Optional session-level data as list of dicts
        equipment_code: Equipment identifier
        supplier_name: Supplier name
        start_date: Analysis start date
        end_date: Analysis end date
        output_dir: Optional output directory

    Returns:
        dict: Result with PowerPoint file path and status
    """
    import asyncio

    try:
        logger.info(
            f"Generating PowerPoint: {analysis_type} for {equipment_code or 'analysis'}"
        )

        # Convert session data to DataFrame if provided
        session_df = None
        if session_data:
            session_df = pd.DataFrame(session_data)

        # Set default output directory
        if not output_dir:
            output_dir = f"output/{analysis_type}"

        # Route to appropriate generator
        if analysis_type.lower() == "runrate":
            from analysis.runrate.reporting.ppt_generator import generate_runrate_ppt

            # Run synchronous PPT generation in executor to avoid blocking
            loop = asyncio.get_event_loop()
            ppt_path = await loop.run_in_executor(
                None,
                lambda: generate_runrate_ppt(
                    metrics=metrics,
                    session_data=session_df,
                    equipment_code=equipment_code,
                    supplier_name=supplier_name,
                    start_date=start_date,
                    end_date=end_date,
                    output_dir=output_dir,
                ),
            )
            logger.info(f"PowerPoint generated: {ppt_path}")
            return {
                "status": "success",
                "message": f"PowerPoint presentation generated successfully: {ppt_path}",
                "ppt_path": ppt_path,
                "output_files": {"ppt": ppt_path},
                "analysis_type": analysis_type,
                "equipment_code": equipment_code,
            }
        else:
            return {
                "status": "error",
                "error": f"PowerPoint generation not yet supported for: {analysis_type}",
                "supported_types": ["runrate"],
                "message": "Currently only RunRate analysis supports PowerPoint generation",
            }

    except Exception as e:
        logger.error(f"PowerPoint generation error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to generate PowerPoint: {str(e)}",
        }
