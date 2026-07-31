"""
RunRate Analysis Module (Refactored).

A modular, async-ready RunRate analysis system for manufacturing analytics.

Main Entry Points:
- run_analysis_api: Synchronous entry point (FastAPI compatible)
- run_analysis_async: Asynchronous entry point (for concurrent operations)
- analyze_runrate: Alias for run_analysis_api (backward compatibility)

Architecture:
- core/: Business logic modules (data loading, processing, session analysis)
- reporting/: Report generation (Excel, charts)
- utils/: Utility functions (time formatting, etc.)
- models/: Data models and configuration

Example Usage:
    >>> from runrate import run_analysis_api
    >>>
    >>> results = run_analysis_api(
    ...     supplier_name="ACME Corp",
    ...     equipment_code="MX-7104",
    ...     start_date="2024-01-01",
    ...     end_date="2024-12-31"
    ... )
    >>>
    >>> print(f"Efficiency: {results['metrics']['efficiency_percentage']}%")
    >>> print(f"Output: {results['output_files'][0]}")

Async Example:
    >>> import asyncio
    >>> from runrate import run_analysis_async
    >>>
    >>> async def analyze():
    ...     results = await run_analysis_async(
    ...         supplier_name="ACME Corp",
    ...         equipment_code="MX-7104"
    ...     )
    ...     return results
    >>>
    >>> results = asyncio.run(analyze())
"""

from .api import analyze_runrate, run_analysis_api, run_analysis_async

# Re-export models for external use
from .models import RunRateConfig, RunRateResults, SessionMetrics

# Re-export utilities
from .utils import format_time_readable, format_time_readable_seconds

# Version info
__version__ = "2.0.0"  # Refactored version
__author__ = "Manufacturing Analytics Team"


__all__ = [
    # Main API
    "run_analysis_api",
    "run_analysis_async",
    "analyze_runrate",
    # Models
    "RunRateConfig",
    "RunRateResults",
    "SessionMetrics",
    # Utilities
    "format_time_readable",
    "format_time_readable_seconds",
    # Metadata
    "__version__",
    "__author__",
]
