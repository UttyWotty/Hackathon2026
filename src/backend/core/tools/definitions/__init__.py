"""
Tool definitions package aggregating all domain-specific tool configurations.

Combines analytics, data, visualization, communication, scheduler, and presentation
tools into a unified TOOLS list for Claude/Bedrock API integration.
"""

from typing import Any, Dict, List

from .analytics import ANALYTICS_TOOLS
from .communication import COMMUNICATION_TOOLS
from .data import DATA_TOOLS
from .insights import INSIGHTS_TOOLS
from .presentation import PRESENTATION_TOOLS
from .scheduler import SCHEDULER_TOOLS
from .visualization import VISUALIZATION_TOOLS

# Aggregate all tools into single list
TOOLS: List[Dict[str, Any]] = (
    DATA_TOOLS
    + ANALYTICS_TOOLS
    + INSIGHTS_TOOLS
    + PRESENTATION_TOOLS
    + COMMUNICATION_TOOLS
    + SCHEDULER_TOOLS
    + VISUALIZATION_TOOLS
)

# Re-export individual tool lists for direct access
__all__ = [
    "TOOLS",
    "ANALYTICS_TOOLS",
    "DATA_TOOLS",
    "INSIGHTS_TOOLS",
    "VISUALIZATION_TOOLS",
    "COMMUNICATION_TOOLS",
    "SCHEDULER_TOOLS",
    "PRESENTATION_TOOLS",
]
