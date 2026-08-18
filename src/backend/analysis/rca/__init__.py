"""
Root Cause Analysis (RCA) Module

Comprehensive root cause analysis for manufacturing issues combining:
- Pareto analysis to identify top issues
- 5 Whys methodology for deep-dive investigation
- Downtime and scrap analysis
- Time pattern detection
- Actionable recommendations

Author: Utku Gulbardak
Date: 2025-10-27
"""

from .api import run_analysis_api

__all__ = ["run_analysis_api"]

__version__ = "1.0.0"
