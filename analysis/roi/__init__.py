"""
ROI Analysis Module
===================

Comprehensive ROI (Return on Investment) analysis for manufacturing operations.

This module provides duration efficiency analysis, cost impact calculation,
and professional Excel report generation.

Author: Utku Gulbardak
Date: 2025-10-24
"""

from .api import ROIAnalyzer
from .classifier import CycleTimeClassifier
from .config import ROIAnalysisConfig
from .database import ROIDatabase
from .metrics import ROIMetricsCalculator
from .preprocessor import ROIPreprocessor
from .report_generator import ROIReportGenerator

__version__ = "2.0.0"
__author__ = "Utku Gulbardak"

__all__ = [
    "ROIAnalysisConfig",
    "ROIAnalyzer",
    "ROIDatabase",
    "ROIPreprocessor",
    "CycleTimeClassifier",
    "ROIMetricsCalculator",
    "ROIReportGenerator",
]
