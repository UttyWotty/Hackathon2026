"""Weekly Comparison Tools for MCP Protocol
========================================

Provides LLM-accessible tools for generating weekly comparison reports
across RunRate and Capacity analyses.

Weeks are defined as Friday to Thursday (midnight).

Author: Utku Gulbardak
Date: 2025-11-28
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def get_friday_to_thursday_week(date: datetime) -> Tuple[datetime, datetime]:
    """Get the Friday-to-Thursday week containing the given date.

    Week runs from Friday 00:00:00 to Thursday 23:59:59.

    Args:
        date: Any date within the week

    Returns:
        Tuple of (friday_start, thursday_end) as datetime objects
    """
    # Find the most recent Friday (or today if it's Friday)
    days_since_friday = (date.weekday() - 4) % 7  # Friday is 4
    if days_since_friday == 0 and date.hour == 0 and date.minute == 0:
        # If it's Friday at midnight, use that date
        friday = date.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Go back to the most recent Friday
        friday = date - timedelta(days=days_since_friday)
        friday = friday.replace(hour=0, minute=0, second=0, microsecond=0)

    # Thursday is 6 days after Friday
    thursday = friday + timedelta(days=6)
    thursday = thursday.replace(hour=23, minute=59, second=59, microsecond=999999)
    return friday, thursday


def get_current_week_and_previous_week() -> Tuple[Tuple[str, str], Tuple[str, str]]:
    """Get current week (Friday-Thursday) and previous week date ranges.

    Returns:
        Tuple of ((week1_start, week1_end), (week2_start, week2_end))
        where week1 is previous week and week2 is current week
        Dates are formatted as YYYY-MM-DD strings
    """
    today = datetime.now()

    # Current week (Friday to Thursday)
    current_friday, current_thursday = get_friday_to_thursday_week(today)

    # Previous week (Friday to Thursday)
    previous_friday = current_friday - timedelta(days=7)
    previous_thursday = current_thursday - timedelta(days=7)

    # Format as strings (YYYY-MM-DD)
    week2_dates = (
        current_friday.strftime("%Y-%m-%d"),
        current_thursday.strftime("%Y-%m-%d"),
    )
    week1_dates = (
        previous_friday.strftime("%Y-%m-%d"),
        previous_thursday.strftime("%Y-%m-%d"),
    )
    return week1_dates, week2_dates


def parse_week_date(date_str: str) -> Tuple[str, str]:
    """Parse a date string and return the Friday-Thursday week containing it.

    Args:
        date_str: Date string (YYYY-MM-DD) - any date within the week

    Returns:
        Tuple of (friday_start, thursday_end) as YYYY-MM-DD strings
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")
    friday, thursday = get_friday_to_thursday_week(date)
    return (
        friday.strftime("%Y-%m-%d"),
        thursday.strftime("%Y-%m-%d"),
    )


async def generate_weekly_comparison_ppt(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    week1_start_date: Optional[str] = None,
    week1_end_date: Optional[str] = None,
    week2_start_date: Optional[str] = None,
    week2_end_date: Optional[str] = None,
    week2_reference_date: Optional[
        str
    ] = None,  # Any date in week 2, auto-calculates Friday-Thursday
    client: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate weekly comparison PowerPoint report.

    Weeks are defined as Friday to Thursday (midnight).
    If dates are not provided, uses current week vs previous week.
    If week2_reference_date is provided, calculates that week and previous week.

    Runs RunRate and Capacity analyses for both weeks, then creates
    a comparison PowerPoint in newsletter format.

    Args:
        equipment_code: Equipment identifier
        supplier_name: Supplier/client name
        week1_start_date: Week 1 start date (YYYY-MM-DD, Friday) - optional
        week1_end_date: Week 1 end date (YYYY-MM-DD, Thursday) - optional
        week2_start_date: Week 2 start date (YYYY-MM-DD, Friday) - optional
        week2_end_date: Week 2 end date (YYYY-MM-DD, Thursday) - optional
        week2_reference_date: Any date in week 2 (YYYY-MM-DD) - auto-calculates Friday-Thursday week
        client: Optional client schema name
        output_dir: Optional output directory

    Returns:
        dict: Result with PowerPoint file path and comparison data
    """
    try:
        # Auto-calculate weeks if not provided
        if week2_reference_date:
            # Calculate week 2 from reference date
            week2_start_date, week2_end_date = parse_week_date(week2_reference_date)
            # Week 1 is 7 days before
            week2_start = datetime.strptime(week2_start_date, "%Y-%m-%d")
            week1_start = week2_start - timedelta(days=7)
            week1_end = week1_start + timedelta(days=6)
            week1_start_date = week1_start.strftime("%Y-%m-%d")
            week1_end_date = week1_end.strftime("%Y-%m-%d")
        elif not all(
            [week1_start_date, week1_end_date, week2_start_date, week2_end_date]
        ):
            # Use current week vs previous week
            (week1_start_date, week1_end_date), (week2_start_date, week2_end_date) = (
                get_current_week_and_previous_week()
            )

        logger.info(
            f"Auto-calculated weeks: Week 1: {week1_start_date} to {week1_end_date}, "
            f"Week 2: {week2_start_date} to {week2_end_date}"
        )
        logger.info(
            f"Generating weekly comparison: {equipment_code} "
            f"(Week 1: {week1_start_date} to {week1_end_date}, "
            f"Week 2: {week2_start_date} to {week2_end_date})"
        )

        # Import analysis functions
        from services.config.features.analytics.tools.capacity_tools import (
            run_capacity_analysis,
        )
        from services.config.features.analytics.tools.runrate_tools import (
            run_runrate_analysis,
        )

        # Run analyses for Week 1
        logger.info("Running Week 1 analyses...")
        week1_runrate = await run_runrate_analysis(
            equipment_codes=[equipment_code],
            start_date=week1_start_date,
            end_date=week1_end_date,
            supplier_names=[supplier_name] if supplier_name else None,
            client=client,
        )

        week1_capacity = await run_capacity_analysis(
            equipment_codes=[equipment_code],
            start_date=week1_start_date,
            end_date=week1_end_date,
            supplier_names=[supplier_name] if supplier_name else None,
            client=client,
        )

        # Run analyses for Week 2
        logger.info("Running Week 2 analyses...")
        week2_runrate = await run_runrate_analysis(
            equipment_codes=[equipment_code],
            start_date=week2_start_date,
            end_date=week2_end_date,
            supplier_names=[supplier_name] if supplier_name else None,
            client=client,
        )

        week2_capacity = await run_capacity_analysis(
            equipment_codes=[equipment_code],
            start_date=week2_start_date,
            end_date=week2_end_date,
            supplier_names=[supplier_name] if supplier_name else None,
            client=client,
        )

        # Check for errors
        if week1_runrate.get("status") != "success":
            return {
                "status": "error",
                "error": f"Week 1 RunRate analysis failed: {week1_runrate.get('error')}",
            }

        if week1_capacity.get("status") != "success":
            return {
                "status": "error",
                "error": f"Week 1 Capacity analysis failed: {week1_capacity.get('error')}",
            }

        if week2_runrate.get("status") != "success":
            return {
                "status": "error",
                "error": f"Week 2 RunRate analysis failed: {week2_runrate.get('error')}",
            }

        if week2_capacity.get("status") != "success":
            return {
                "status": "error",
                "error": f"Week 2 Capacity analysis failed: {week2_capacity.get('error')}",
            }

        # Prepare data for PPT generation
        # Include session data for accurate MTTR/MTBF calculation
        week1_data = {
            "runrate": week1_runrate.get("metrics", {}),
            "runrate_session_data": week1_runrate.get(
                "session_metrics"
            ),  # Session-level data for MTTR/MTBF
            "capacity": week1_capacity.get("metrics", {}),
        }

        week2_data = {
            "runrate": week2_runrate.get("metrics", {}),
            "runrate_session_data": week2_runrate.get(
                "session_metrics"
            ),  # Session-level data for MTTR/MTBF
            "capacity": week2_capacity.get("metrics", {}),
        }

        # Generate PowerPoint
        from analysis.shared.weekly_comparison_ppt import generate_weekly_comparison_ppt

        if not output_dir:
            output_dir = "output/comparison"

        # Run PPT generation in executor (it's synchronous)
        loop = asyncio.get_event_loop()
        ppt_path = await loop.run_in_executor(
            None,
            lambda: generate_weekly_comparison_ppt(
                equipment_code=equipment_code,
                supplier_name=supplier_name
                or equipment_code,  # Use equipment_code as fallback
                week1_data=week1_data,
                week2_data=week2_data,
                week1_dates=(week1_start_date, week1_end_date),
                week2_dates=(week2_start_date, week2_end_date),
                output_dir=output_dir,
            ),
        )
        logger.info(f"Weekly comparison PowerPoint generated: {ppt_path}")
        return {
            "status": "success",
            "message": "Weekly comparison PowerPoint generated successfully",
            "ppt_path": ppt_path,
            "output_files": {
                "ppt": ppt_path,
            },
            "equipment_code": equipment_code,
            "week1": {
                "dates": f"{week1_start_date} to {week1_end_date}",
                "runrate": week1_runrate.get("metrics", {}),
                "capacity": week1_capacity.get("metrics", {}),
            },
            "week2": {
                "dates": f"{week2_start_date} to {week2_end_date}",
                "runrate": week2_runrate.get("metrics", {}),
                "capacity": week2_capacity.get("metrics", {}),
            },
        }

    except Exception as e:
        logger.error(f"Weekly comparison error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to generate weekly comparison: {str(e)}",
        }
