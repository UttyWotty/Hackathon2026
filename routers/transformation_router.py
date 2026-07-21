"""
Transformation Router - Data Quality & ETL

Provides data transformation capabilities:
- Data cleaning (duplicates, nulls, outliers)
- Data validation (type checking, quality scores)
- ETL pipelines (multi-step transformations)
- Data quality reports

Uses: services/infrastructure/transformation/
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, validator  # type: ignore[import-untyped]

from services.infrastructure.transformation.data_cleaner import DataCleaner
from services.infrastructure.transformation.pipeline import run_configured_pipeline
from services.infrastructure.transformation.scaling import (
    normalize_columns,
    standardize_columns,
)
from services.infrastructure.transformation.transformer import DataTransformer
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

# Constants
INPUT_DATA_EMPTY_ERROR = "Input data is empty"

router = APIRouter()

# Initialize transformation components
cleaner = DataCleaner()
transformer = DataTransformer()


# Request Models
class CleanDataRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="Data to clean")
    remove_duplicates: bool = Field(True, description="Remove duplicate rows")
    handle_nulls: str = Field(
        "drop", description="How to handle nulls: 'drop', 'fill', 'interpolate'"
    )
    fill_value: Optional[Any] = Field(
        None, description="Value to fill nulls with (if handle_nulls='fill')"
    )
    detect_outliers: bool = Field(False, description="Detect and handle outliers")
    outlier_method: str = Field(
        "iqr", description="Outlier detection method: 'iqr', 'zscore'"
    )

    @validator("handle_nulls")
    def validate_handle_nulls(cls, v):
        allowed = ["drop", "fill", "interpolate", "none"]
        if v not in allowed:
            raise ValueError(f"handle_nulls must be one of: {allowed}")
        return v

    @validator("outlier_method")
    def validate_outlier_method(cls, v):
        allowed = ["iqr", "zscore"]
        if v not in allowed:
            raise ValueError(f"outlier_method must be one of: {allowed}")
        return v

    @validator("data")
    def validate_data_size(cls, v):
        if len(v) > 100000:
            raise ValueError("Data too large (max 100,000 rows)")
        if len(v) == 0:
            raise ValueError("Data cannot be empty")
        return v


class ValidateDataRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="Data to validate")
    required_columns: Optional[List[str]] = Field(
        None, description="Columns that must be present"
    )
    type_checks: Optional[Dict[str, str]] = Field(
        None, description="Expected types per column"
    )
    check_nulls: bool = Field(True, description="Check for null values")
    check_duplicates: bool = Field(True, description="Check for duplicates")


class TransformDataRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="Data to transform")
    operations: List[Dict[str, Any]] = Field(
        ..., description="Transformation operations to apply"
    )


class PipelineRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="Input data for pipeline")
    pipeline_name: str = Field(..., description="Pipeline to execute")
    config: Optional[Dict[str, Any]] = Field(None, description="Pipeline configuration")


@router.get("/", summary="Transformation Service Info")
async def transformation_info():
    """Get information about the transformation service."""
    return {
        "service": "Transformation Service",
        "description": "Data quality, cleaning, and ETL capabilities",
        "capabilities": [
            "Data Cleaning (duplicates, nulls, outliers)",
            "Data Validation (types, quality checks)",
            "Data Transformation (normalize, aggregate, pivot)",
            "ETL Pipelines (multi-step transformations)",
        ],
        "endpoints": {
            "clean": "POST /transformation/clean - Clean and prepare data",
            "validate": "POST /transformation/validate - Validate data quality",
            "transform": "POST /transformation/transform - Apply transformations",
            "pipeline": "POST /transformation/pipeline - Run ETL pipeline",
        },
    }


@router.post("/clean", summary="Clean Data")
async def clean_data(request: CleanDataRequest):
    """
    Clean and prepare manufacturing data for analysis.

    Operations:
    - Remove duplicate records
    - Handle missing values (drop, fill, interpolate)
    - Detect and handle outliers
    - Fix data types

    Returns cleaned data with statistics about what was cleaned.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail=INPUT_DATA_EMPTY_ERROR)

        original_rows = len(df)
        cleaning_stats = {
            "original_rows": original_rows,
            "duplicates_removed": 0,
            "nulls_handled": 0,
            "outliers_handled": 0,
        }

        # Remove duplicates
        if request.remove_duplicates:
            df_clean, stats = cleaner.remove_duplicates(df)
            df = df_clean
            cleaning_stats["duplicates_removed"] = stats["duplicates_removed"]

        # Handle nulls
        if request.handle_nulls != "none":
            df_clean, stats = cleaner.handle_missing_values(
                df, strategy=request.handle_nulls, fill_value=request.fill_value
            )
            df = df_clean
            cleaning_stats["nulls_handled"] = stats.get("nulls_handled", 0)

        # Handle outliers
        if request.detect_outliers:
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            if numeric_cols:
                df_clean, stats = cleaner.remove_outliers(
                    df, columns=numeric_cols, method=request.outlier_method
                )
                df = df_clean
                cleaning_stats["outliers_handled"] = stats.get("outliers_removed", 0)

        cleaning_stats["final_rows"] = len(df)
        cleaning_stats["rows_removed"] = original_rows - len(df)
        cleaning_stats["data_loss_percentage"] = round(
            (
                (cleaning_stats["rows_removed"] / original_rows * 100)
                if original_rows > 0
                else 0
            ),
            2,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "statistics": cleaning_stats,
            "cleaned_data": df.to_dict("records"),
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Cleaned {original_rows} rows → {len(df)} rows ({cleaning_stats['data_loss_percentage']}% data loss)",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data cleaning error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Data cleaning failed. Please check your input data."
        )
        raise HTTPException(status_code=500, detail=error_msg)


def _check_required_columns(
    df: pd.DataFrame,
    required_columns: Optional[List[str]],
    validation_results: Dict[str, Any],
) -> None:
    """Check if required columns are present in the dataframe."""
    if not required_columns:
        return

    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        validation_results["is_valid"] = False
        validation_results["issues"].append(
            {
                "type": "missing_columns",
                "details": f"Required columns not found: {missing_cols}",
            }
        )


def _check_data_types(
    df: pd.DataFrame,
    type_checks: Optional[Dict[str, str]],
    validation_results: Dict[str, Any],
) -> None:
    """Check if data types match expected types."""
    if not type_checks:
        return

    type_mismatches = []
    for col, expected_type in type_checks.items():
        if col in df.columns:
            actual_type = str(df[col].dtype)
            if expected_type not in actual_type:
                type_mismatches.append(
                    {
                        "column": col,
                        "expected": expected_type,
                        "actual": actual_type,
                    }
                )
    if type_mismatches:
        validation_results["warnings"].append(
            {"type": "type_mismatches", "details": type_mismatches}
        )


def _check_nulls(
    df: pd.DataFrame, check_nulls: bool, validation_results: Dict[str, Any]
) -> None:
    """Check for null values in the dataframe."""
    if not check_nulls:
        return

    null_counts = df.isnull().sum()
    cols_with_nulls = null_counts[null_counts > 0].to_dict()
    if cols_with_nulls:
        validation_results["warnings"].append(
            {"type": "null_values", "details": cols_with_nulls}
        )
        validation_results["statistics"]["total_nulls"] = int(null_counts.sum())


def _check_duplicates(
    df: pd.DataFrame, check_duplicates: bool, validation_results: Dict[str, Any]
) -> None:
    """Check for duplicate rows in the dataframe."""
    if not check_duplicates:
        return

    duplicate_count = df.duplicated().sum()
    if duplicate_count > 0:
        validation_results["warnings"].append(
            {
                "type": "duplicates",
                "details": f"Found {duplicate_count} duplicate rows",
            }
        )
        validation_results["statistics"]["duplicates"] = int(duplicate_count)


def _calculate_quality_score(validation_results: Dict[str, Any]) -> float:
    """Calculate data quality score based on issues and warnings."""
    quality_score = 100.0
    if validation_results["issues"]:
        quality_score -= len(validation_results["issues"]) * 20
    if validation_results["warnings"]:
        quality_score -= len(validation_results["warnings"]) * 10
    return max(0, quality_score)


@router.post("/validate", summary="Validate Data Quality")
async def validate_data(request: ValidateDataRequest):
    """
    Validate manufacturing data quality and integrity.

    Checks:
    - Required columns present
    - Data types correct
    - No unexpected nulls
    - No duplicates
    - Data quality score

    Returns validation report with issues found.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail=INPUT_DATA_EMPTY_ERROR)

        validation_results = {
            "is_valid": True,
            "issues": [],
            "warnings": [],
            "statistics": {},
        }

        # Run validation checks
        _check_required_columns(df, request.required_columns, validation_results)
        _check_data_types(df, request.type_checks, validation_results)
        _check_nulls(df, request.check_nulls, validation_results)
        _check_duplicates(df, request.check_duplicates, validation_results)

        # Calculate quality score
        quality_score = _calculate_quality_score(validation_results)
        validation_results["quality_score"] = quality_score
        validation_results["statistics"]["total_rows"] = len(df)
        validation_results["statistics"]["total_columns"] = len(df.columns)

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": (
                "success" if validation_results["is_valid"] else "validation_failed"
            ),
            "validation": validation_results,
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Data quality score: {quality_score}% ({len(validation_results['issues'])} issues, {len(validation_results['warnings'])} warnings)",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data validation error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Data validation failed. Please check your input data."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/transform", summary="Transform Data")
async def transform_data(request: TransformDataRequest):
    """
    Apply custom transformations to data.

    Supported operations:
    - **normalize**: Scale values to 0-1 range
    - **standardize**: Z-score normalization
    - **aggregate**: Group and aggregate data
    - **pivot**: Pivot table operations
    - **filter**: Filter rows based on conditions
    - **map**: Apply custom mappings

    Returns transformed data.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail=INPUT_DATA_EMPTY_ERROR)

        operations_applied = []

        # Apply each transformation
        for operation in request.operations:
            op_type = operation.get("type")
            op_params = operation.get("params", {})

            if op_type == "normalize":
                columns = op_params.get(
                    "columns", df.select_dtypes(include=["number"]).columns.tolist()
                )
                df, _ = normalize_columns(df, columns)
                operations_applied.append({"type": op_type, "columns": columns})

            elif op_type == "standardize":
                columns = op_params.get(
                    "columns", df.select_dtypes(include=["number"]).columns.tolist()
                )
                df, _ = standardize_columns(df, columns)
                operations_applied.append({"type": op_type, "columns": columns})

            elif op_type == "aggregate":
                group_by = op_params.get("group_by", [])
                agg_funcs = op_params.get("agg_funcs", {})
                if group_by and agg_funcs:
                    df = df.groupby(group_by).agg(agg_funcs).reset_index()
                    operations_applied.append({"type": op_type, "group_by": group_by})

            else:
                logger.warning(f"Unknown operation type: {op_type}")

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "operations_applied": operations_applied,
            "original_rows": len(request.data),
            "transformed_rows": len(df),
            "transformed_data": df.to_dict("records"),
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Applied {len(operations_applied)} transformations",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data transformation error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e,
            "Data transformation failed. Please check your transformation operations.",
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/pipeline", summary="Run ETL Pipeline")
async def run_pipeline(request: PipelineRequest):
    """
    Execute a pre-configured ETL pipeline.

    Available pipelines:
    - **manufacturing_etl**: Full manufacturing data pipeline
    - **quality_check**: Data quality validation pipeline
    - **analytics_prep**: Prepare data for analysis

    Pipelines can include multiple cleaning, validation, and transformation steps.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail=INPUT_DATA_EMPTY_ERROR)

        # Build the pipeline from the requested config and execute it
        result = run_configured_pipeline(
            request.pipeline_name, request.config or {}, df
        )

        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("error") or "Pipeline execution failed",
            )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "pipeline": request.pipeline_name,
            "steps_executed": result["steps_executed"],
            "statistics": result["statistics"],
            "output_data": result["output_data"],
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Pipeline '{request.pipeline_name}' completed successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline execution error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Pipeline execution failed. Please check your pipeline configuration."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/health", summary="Transformation Service Health")
async def health_check():
    """Check if transformation service is ready."""
    try:
        components_status = {
            "data_cleaner": "ready" if cleaner else "not_initialized",
            "pipeline": "ready",  # Created per-request
            "transformer": "ready" if transformer else "not_initialized",
        }

        overall_status = (
            "healthy"
            if all(s == "ready" for s in components_status.values())
            else "degraded"
        )

        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "components": components_status,
            "dependencies": {
                "pandas": "available",
                "numpy": "available",
            },
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
