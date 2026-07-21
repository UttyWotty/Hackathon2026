"""
Transformation Pipeline System.

Features:
- Chain multiple transformations
- Save/load pipeline definitions
- Pipeline validation
- Execution history
- Error handling

Author: Utku Gulbardak
Date: 2025-11-12
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from services.infrastructure.transformation.data_cleaner import get_data_cleaner
from services.infrastructure.transformation.transformer import get_data_transformer

logger = logging.getLogger(__name__)


class TransformationPipeline:
    """
    Transformation Pipeline.

    Allows chaining multiple transformations into a pipeline.
    """

    def __init__(self, name: str, description: Optional[str] = None):
        """
        Initialize Pipeline.

        Args:
            name: Pipeline name
            description: Optional description
        """
        self.name = name
        self.description = description
        self.steps: List[Dict[str, Any]] = []
        self.execution_history: List[Dict[str, Any]] = []
        self.created_at = datetime.now().isoformat()

        logger.info(f"✅ Pipeline '{name}' initialized")

    def add_step(
        self,
        step_type: str,
        operation: str,
        parameters: Dict[str, Any],
        description: Optional[str] = None,
    ) -> "TransformationPipeline":
        """
        Add transformation step to pipeline.

        Args:
            step_type: 'cleaning' or 'transformation'
            operation: Operation name (e.g., 'remove_duplicates', 'filter_rows')
            parameters: Operation parameters
            description: Optional step description

        Returns:
            self: For method chaining
        """
        step = {
            "step_number": len(self.steps) + 1,
            "step_type": step_type,
            "operation": operation,
            "parameters": parameters,
            "description": description,
        }

        self.steps.append(step)
        logger.info(f"   Added step {step['step_number']}: {step_type}.{operation}")

        return self

    def execute(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Execute pipeline on DataFrame.

        Args:
            df: Input DataFrame

        Returns:
            dict: Execution result with transformed data and statistics
        """
        start_time = datetime.now()
        current_df = df.copy()

        step_results = []
        cleaner = get_data_cleaner()
        transformer = get_data_transformer()

        logger.info(f"🔄 Executing pipeline '{self.name}' ({len(self.steps)} steps)")

        for step in self.steps:
            step_start = datetime.now()

            try:
                step_type = step["step_type"]
                operation = step["operation"]
                params = step["parameters"]

                logger.info(
                    f"   Step {step['step_number']}/{len(self.steps)}: {step_type}.{operation}"
                )

                # Execute step based on type
                if step_type == "cleaning":
                    if operation == "remove_duplicates":
                        current_df, stats = cleaner.remove_duplicates(
                            current_df, **params
                        )
                    elif operation == "handle_missing_values":
                        current_df, stats = cleaner.handle_missing_values(
                            current_df, **params
                        )
                    elif operation == "remove_outliers":
                        current_df, stats = cleaner.remove_outliers(
                            current_df, **params
                        )
                    else:
                        raise ValueError(f"Unknown cleaning operation: {operation}")

                elif step_type == "transformation":
                    if operation == "select_columns":
                        current_df, stats = transformer.select_columns(
                            current_df, **params
                        )
                    elif operation == "rename_columns":
                        current_df, stats = transformer.rename_columns(
                            current_df, **params
                        )
                    elif operation == "convert_dtypes":
                        current_df, stats = transformer.convert_dtypes(
                            current_df, **params
                        )
                    elif operation == "filter_rows":
                        current_df, stats = transformer.filter_rows(
                            current_df, **params
                        )
                    elif operation == "aggregate_data":
                        current_df, stats = transformer.aggregate_data(
                            current_df, **params
                        )
                    elif operation == "pivot_data":
                        current_df, stats = transformer.pivot_data(current_df, **params)
                    elif operation == "sort_data":
                        current_df, stats = transformer.sort_data(current_df, **params)
                    elif operation == "add_calculated_column":
                        current_df, stats = transformer.add_calculated_column(
                            current_df, **params
                        )
                    else:
                        raise ValueError(
                            f"Unknown transformation operation: {operation}"
                        )

                else:
                    raise ValueError(f"Unknown step type: {step_type}")

                step_duration = (datetime.now() - step_start).total_seconds() * 1000

                step_results.append(
                    {
                        "step_number": step["step_number"],
                        "operation": f"{step_type}.{operation}",
                        "status": "success",
                        "duration_ms": step_duration,
                        "statistics": stats,
                        "rows_after": len(current_df),
                        "columns_after": len(current_df.columns),
                    }
                )

            except Exception as e:
                logger.error(f"   ❌ Step {step['step_number']} failed: {e}")

                step_results.append(
                    {
                        "step_number": step["step_number"],
                        "operation": f"{step_type}.{operation}",
                        "status": "error",
                        "error": str(e),
                    }
                )

                # Record failure in history
                self.execution_history.append(
                    {
                        "timestamp": start_time.isoformat(),
                        "status": "failed",
                        "failed_at_step": step["step_number"],
                        "error": str(e),
                    }
                )

                return {
                    "status": "error",
                    "error": f"Pipeline failed at step {step['step_number']}: {str(e)}",
                    "steps_completed": step["step_number"] - 1,
                    "step_results": step_results,
                }

        total_duration = (datetime.now() - start_time).total_seconds() * 1000

        # Record success in history
        execution_record = {
            "timestamp": start_time.isoformat(),
            "status": "success",
            "duration_ms": total_duration,
            "input_rows": len(df),
            "output_rows": len(current_df),
            "input_columns": len(df.columns),
            "output_columns": len(current_df.columns),
            "steps_executed": len(self.steps),
        }
        self.execution_history.append(execution_record)

        logger.info(f"✅ Pipeline '{self.name}' completed in {total_duration:.2f}ms")

        return {
            "status": "success",
            "pipeline_name": self.name,
            "data": current_df,
            "execution_stats": execution_record,
            "step_results": step_results,
        }

    def validate(self) -> Dict[str, Any]:
        """
        Validate pipeline configuration.

        Returns:
            dict: Validation result
        """
        validation_report = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "steps_checked": len(self.steps),
        }

        if not self.steps:
            validation_report["errors"].append("Pipeline has no steps")
            validation_report["is_valid"] = False

        # Check each step
        valid_cleaning_ops = [
            "remove_duplicates",
            "handle_missing_values",
            "remove_outliers",
        ]
        valid_transformation_ops = [
            "select_columns",
            "rename_columns",
            "convert_dtypes",
            "filter_rows",
            "aggregate_data",
            "pivot_data",
            "sort_data",
            "add_calculated_column",
        ]

        for step in self.steps:
            step_type = step.get("step_type")
            operation = step.get("operation")

            if step_type == "cleaning" and operation not in valid_cleaning_ops:
                validation_report["errors"].append(
                    f"Step {step['step_number']}: Unknown cleaning operation '{operation}'"
                )
                validation_report["is_valid"] = False

            elif (
                step_type == "transformation"
                and operation not in valid_transformation_ops
            ):
                validation_report["errors"].append(
                    f"Step {step['step_number']}: Unknown transformation operation '{operation}'"
                )
                validation_report["is_valid"] = False

            if not step.get("parameters"):
                validation_report["warnings"].append(
                    f"Step {step['step_number']}: No parameters specified"
                )

        return validation_report

    def to_dict(self) -> Dict[str, Any]:
        """
        Export pipeline to dictionary.

        Returns:
            dict: Pipeline configuration
        """
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "steps": self.steps,
            "total_executions": len(self.execution_history),
        }

    def to_json(self, filepath: Optional[str] = None) -> str:
        """
        Export pipeline to JSON.

        Args:
            filepath: Optional file path to save to

        Returns:
            str: JSON string
        """
        pipeline_json = json.dumps(self.to_dict(), indent=2)

        if filepath:
            with open(filepath, "w") as f:
                f.write(pipeline_json)
            logger.info(f"✅ Pipeline saved to {filepath}")

        return pipeline_json

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "TransformationPipeline":
        """
        Create pipeline from dictionary.

        Args:
            config: Pipeline configuration

        Returns:
            TransformationPipeline: Pipeline instance
        """
        pipeline = cls(name=config["name"], description=config.get("description"))

        for step in config.get("steps", []):
            pipeline.add_step(
                step_type=step["step_type"],
                operation=step["operation"],
                parameters=step["parameters"],
                description=step.get("description"),
            )

        return pipeline

    @classmethod
    def from_json(cls, json_str: str) -> "TransformationPipeline":
        """
        Create pipeline from JSON string.

        Args:
            json_str: JSON string or file path

        Returns:
            TransformationPipeline: Pipeline instance
        """
        # Try to load from file first
        try:
            with open(json_str, "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            # Treat as JSON string
            config = json.loads(json_str)

        return cls.from_dict(config)

    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent execution history.

        Args:
            limit: Max number of records

        Returns:
            list: Execution records
        """
        return self.execution_history[-limit:]

    def clear_history(self):
        """Clear execution history."""
        self.execution_history = []
        logger.info(f"🗑️  Cleared execution history for pipeline '{self.name}'")


# Keys a configured pipeline step must provide; the rest are optional.
REQUIRED_STEP_KEYS = ("step_type", "operation")
PIPELINE_ERROR_STATUS = "error"


def _config_error(message: str) -> Dict[str, Any]:
    """Build the API-shaped error result for an invalid pipeline config."""
    return {
        "status": PIPELINE_ERROR_STATUS,
        "error": message,
        "steps_executed": [],
        "statistics": {},
        "output_data": [],
    }


def _validate_steps(steps: Any) -> Optional[str]:
    """Return an error message if the steps config is malformed, else None.

    Guards the caller-supplied ``steps`` before any step is built so malformed
    client input yields a caught error (mapped to HTTP 400) rather than an
    uncaught ``KeyError``/``TypeError`` surfacing as a 500.
    """
    if not isinstance(steps, list):
        return "Pipeline 'steps' must be a list"
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return f"Pipeline step {index} must be an object"
        for key in REQUIRED_STEP_KEYS:
            if key not in step:
                return f"Pipeline step {index} is missing required key '{key}'"
    return None


def run_configured_pipeline(
    name: str, config: Dict[str, Any], df: pd.DataFrame
) -> Dict[str, Any]:
    """Build a pipeline from a config dict, execute it, and normalize the result.

    The config may carry a ``steps`` list, each entry shaped like a ``from_dict``
    step (``step_type``, ``operation``, ``parameters``, optional ``description``);
    an absent or empty list runs zero steps and returns the input unchanged. A
    malformed ``steps`` config returns an ``error`` result rather than raising.

    Args:
        name: Pipeline name.
        config: Pipeline configuration (may contain a ``steps`` list).
        df: Input DataFrame.

    Returns:
        dict: ``status``/``error`` plus API-ready ``steps_executed``,
        ``statistics``, and record-oriented ``output_data``.
    """
    steps = config.get("steps", [])
    validation_error = _validate_steps(steps)
    if validation_error is not None:
        return _config_error(validation_error)

    pipeline = TransformationPipeline(name=name)
    for step in steps:
        pipeline.add_step(
            step_type=step["step_type"],
            operation=step["operation"],
            parameters=step.get("parameters", {}),
            description=step.get("description"),
        )
    result = pipeline.execute(df)
    output_df = result.get("data")
    return {
        "status": result.get("status", "success"),
        "error": result.get("error"),
        "steps_executed": result.get("step_results", []),
        "statistics": result.get("execution_stats", {}),
        "output_data": (output_df.to_dict("records") if output_df is not None else []),
    }


# Pipeline registry
_pipelines: Dict[str, TransformationPipeline] = {}


def register_pipeline(pipeline: TransformationPipeline):
    """
    Register pipeline in global registry.

    Args:
        pipeline: Pipeline to register
    """
    _pipelines[pipeline.name] = pipeline
    logger.info(f"✅ Registered pipeline: {pipeline.name}")


def get_pipeline(name: str) -> Optional[TransformationPipeline]:
    """
    Get pipeline from registry.

    Args:
        name: Pipeline name

    Returns:
        TransformationPipeline or None
    """
    return _pipelines.get(name)


def list_pipelines() -> List[str]:
    """
    List all registered pipelines.

    Returns:
        list: Pipeline names
    """
    return list(_pipelines.keys())
