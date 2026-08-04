"""
Direct Tool Dispatcher - Executes tools directly without HTTP calls.

Maintains separation of concerns: scheduler calls tools directly, not through HTTP.
This eliminates the architectural issue of calling API endpoints from within the API.

Fixed async/await pattern: Uses await directly instead of get_event_loop() + run_until_complete()
to prevent deadlocks and event loop issues.
"""

import asyncio
import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

# Tool registry - maps tool names to their functions
# Lazy loading: functions are imported when needed to avoid circular imports
_TOOL_REGISTRY: Dict[str, Callable] = {}

# Tool import mapping - maps tool names to (module_path, function_name) tuples
# This eliminates code duplication by using a data-driven approach
_ANALYTICS_TOOL_IMPORTS: Dict[str, tuple] = {
    "run_roi_analysis": (
        "services.config.features.analytics.tools.roi_tools",
        "run_roi_analysis",
    ),
    "run_rca_analysis": (
        "services.config.features.analytics.tools.rca_tools",
        "run_rca_analysis",
    ),
    "run_ct_efficiency_analysis": (
        "services.config.features.analytics.tools.ct_efficiency_tools",
        "run_ct_efficiency_analysis",
    ),
    "run_ct_deviation_analysis": (
        "services.config.features.analytics.tools.ct_deviation_tools",
        "run_ct_deviation_analysis",
    ),
    "run_tooling_eol_analysis": (
        "services.config.features.analytics.tools.tooling_eol_tools",
        "run_tooling_eol_analysis",
    ),
    "refresh_demo_table": (
        "services.config.features.analytics.tools.master_table_tools",
        "refresh_demo_table",
    ),
    "generate_presentation": (
        "services.config.features.analytics.tools.ppt_tools",
        "generate_presentation",
    ),
}

_DATA_TOOL_IMPORTS: Dict[str, tuple] = {
    "run_sql_query": (
        "services.config.features.sql.tools.query_tools",
        "run_sql_query",
    ),
    "list_tables": ("services.config.features.sql.tools.schema_tools", "list_tables"),
    "describe_table": (
        "services.config.features.sql.tools.schema_tools",
        "describe_table",
    ),
    "get_master_table_progress": (
        "services.config.features.analytics.tools.master_table_tools",
        "get_log_progress",
    ),
}

_PLATFORM_TOOL_IMPORTS: Dict[str, tuple] = {
    "send_email_report": ("core.tools.email_sender", "send_email_with_attachments"),
    "create_chart": ("services.visualization.visualization_tools", "create_chart"),
    "create_manufacturing_dashboard": (
        "services.visualization.visualization_tools",
        "create_manufacturing_dashboard",
    ),
    "schedule_job": ("services.infrastructure.scheduler.job_service", "schedule_job"),
    "list_scheduled_jobs": (
        "services.infrastructure.scheduler.job_service",
        "list_scheduled_jobs",
    ),
    "cancel_job": ("services.infrastructure.scheduler.job_service", "cancel_job"),
}

_INSIGHTS_TOOL_IMPORTS: Dict[str, tuple] = {
    "get_plant_health_snapshot": (
        "services.config.features.insights.tools.plant_health_tools",
        "get_plant_health_snapshot",
    ),
    "compare_periods": (
        "services.config.features.insights.tools.period_tools",
        "compare_periods",
    ),
    "find_top_movers": (
        "services.config.features.insights.tools.period_tools",
        "find_top_movers",
    ),
    "validate_approved_cts": (
        "services.config.features.insights.tools.ct_validation_tools",
        "validate_approved_cts",
    ),
    "data_freshness_report": (
        "services.config.features.insights.tools.freshness_tools",
        "data_freshness_report",
    ),
    "data_quality_audit": (
        "services.config.features.insights.tools.quality_tools",
        "data_quality_audit",
    ),
    "get_mold_history": (
        "services.config.features.insights.tools.mold_tools",
        "get_mold_history",
    ),
    "maintenance_impact_analysis": (
        "services.config.features.insights.tools.mold_tools",
        "maintenance_impact_analysis",
    ),
    "trace_work_order": (
        "services.config.features.insights.tools.work_order_tools",
        "trace_work_order",
    ),
    "forecast_metric": (
        "services.config.features.insights.tools.forecast_tools",
        "forecast_metric",
    ),
    "simulate_savings": (
        "services.config.features.insights.tools.savings_tools",
        "simulate_savings",
    ),
    "get_metric_definitions": (
        "services.config.features.insights.tools.knowledge_tools",
        "get_metric_definitions",
    ),
    "save_insight": (
        "services.config.features.insights.tools.knowledge_tools",
        "save_insight",
    ),
    "get_insights": (
        "services.config.features.insights.tools.knowledge_tools",
        "get_insights",
    ),
    "get_recent_analysis_results": (
        "services.config.features.insights.tools.results_tools",
        "get_recent_analysis_results",
    ),
}

_TOOL_IMPORTS: Dict[str, tuple] = {
    **_ANALYTICS_TOOL_IMPORTS,
    **_DATA_TOOL_IMPORTS,
    **_PLATFORM_TOOL_IMPORTS,
    **_INSIGHTS_TOOL_IMPORTS,
}


def _get_tool_function(tool_name: str) -> Callable:
    """
    Get tool function from registry, importing if necessary.

    Uses a registry pattern to eliminate code duplication.
    Tools are lazily imported to avoid circular dependencies.

    Args:
        tool_name: Name of the tool

    Returns:
        Callable: Tool function

    Raises:
        ValueError: If tool not found
    """
    # Check registry first (cached)
    if tool_name in _TOOL_REGISTRY:
        return _TOOL_REGISTRY[tool_name]

    # Check if tool is in import mapping
    if tool_name not in _TOOL_IMPORTS:
        raise ValueError(f"Unknown tool: {tool_name}")

    # Dynamically import tool using registry pattern
    module_path, function_name = _TOOL_IMPORTS[tool_name]

    try:
        # Import module dynamically
        module = __import__(module_path, fromlist=[function_name])
        # Get function from module
        tool_func = getattr(module, function_name)
        # Cache in registry
        _TOOL_REGISTRY[tool_name] = tool_func
        return tool_func
    except (ImportError, AttributeError) as e:
        raise ValueError(f"Failed to import tool '{tool_name}': {e}")


async def dispatch_tool_direct(
    tool_name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Dispatch tool execution directly without HTTP calls.

    Fixed async pattern: Now properly async, uses await directly instead of
    get_event_loop() + run_until_complete() to prevent deadlocks.

    Separation of concerns:
    - This module handles direct function calls
    - No HTTP overhead or circular dependencies
    - Tools are imported and called directly
    - Proper async/await pattern prevents event loop issues

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        dict: Tool execution result
    """
    try:
        # Get tool function from registry
        tool_func = _get_tool_function(tool_name)

        # Handle async vs sync tools properly
        if asyncio.iscoroutinefunction(tool_func):
            # Async tool - use await directly (proper async pattern)
            result = await tool_func(**arguments)
            return result
        else:
            # Sync tool - run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: tool_func(**arguments))
            return result

    except ValueError as e:
        # Unknown tool - the registry is the single source of truth. The old HTTP
        # fallback called this same server and deadlocked the event loop.
        logger.warning("Unknown tool requested: %s", tool_name)
        return {
            "status": "error",
            "error": str(e),
            "known_tools": sorted(_TOOL_IMPORTS),
        }

    except Exception as e:
        logger.error("Tool dispatch error for %s: %s", tool_name, e, exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
