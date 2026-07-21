"""
Tooling End-of-Life Prediction Module.

This module provides comprehensive tooling end-of-life prediction capabilities,
including data loading, rate calculation, utilization analysis, and prediction.

## Architecture

The module is organized into several subpackages:

- **models**: Data models and configuration (ELCPrediction, constants)
- **core**: Core business logic (data loading, calculations, predictions)
- **reporting**: Report generation (HTML output)
- **api**: High-level API for external integration

## Quick Start

```python
from tooling_eol import run_analysis_api

# Run full EOL prediction
result = run_analysis_api(
    save_csv=True,
    save_html=True,
    tooling_family="Injection Molding"
)

if result["status"] == "success":
    predictions_df = result["predictions"]
    print(f"Generated predictions for {len(predictions_df)} molds")
```

## Legacy Interface

For backwards compatibility with the original predictor.py:

```python
from tooling_eol import main

predictions = main(save_csv=True, save_html=False)
```

Author: Utku Gulbardak
Date: 2025-10-27
"""

from .api import main, run_analysis_api
from .core import (
    create_snowpark_session,
    predict_end_of_life,
    predict_end_of_life_for_mold,
    read_maintenance_events,
    read_master_shot_table,
    read_mold_table,
)
from .models.config import (
    ELCPrediction,
    get_derate_factor,
    get_design_life,
    get_oee,
    get_utilization_bins,
)
from .reporting import generate_html_report

__all__ = [
    # API functions
    "run_analysis_api",
    "main",
    # Models
    "ELCPrediction",
    # Configuration
    "get_oee",
    "get_utilization_bins",
    "get_derate_factor",
    "get_design_life",
    # Core functions
    "create_snowpark_session",
    "read_master_shot_table",
    "read_maintenance_events",
    "read_mold_table",
    "predict_end_of_life",
    "predict_end_of_life_for_mold",
    # Reporting
    "generate_html_report",
]

__version__ = "2.0.0"
