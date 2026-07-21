"""Unit tests for the run_configured_pipeline adapter used by /transformation/pipeline.

Exercises the config-to-pipeline builder directly on small DataFrames, covering
the zero-step passthrough, a valid step, and malformed step configs that must
return a caught ``error`` result (mapped to HTTP 400) instead of raising. No I/O
and no mocks.
"""

from typing import Any, Dict

import pandas as pd  # type: ignore[import-untyped]

from services.infrastructure.transformation.pipeline import (
    PIPELINE_ERROR_STATUS,
    run_configured_pipeline,
)

SAMPLE_FRAME = pd.DataFrame({"a": [1, 2], "b": [3, 4]})


def _run(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the adapter against the shared sample frame."""
    return run_configured_pipeline("test_pipeline", config, SAMPLE_FRAME)


def test_absent_steps_returns_input_unchanged() -> None:
    """A config with no steps runs zero steps and passes the frame through."""
    result = _run({})
    assert result["status"] == "success"
    assert result["output_data"] == [{"a": 1, "b": 3}, {"a": 2, "b": 4}]
    assert result["steps_executed"] == []


def test_valid_step_executes() -> None:
    """A well-formed step is built and executed, transforming the frame."""
    config = {
        "steps": [
            {
                "step_type": "transformation",
                "operation": "select_columns",
                "parameters": {"columns": ["a"]},
            }
        ]
    }
    result = _run(config)
    assert result["status"] == "success"
    assert result["output_data"] == [{"a": 1}, {"a": 2}]


def test_step_missing_required_key_returns_error() -> None:
    """A step lacking 'operation' returns an error result rather than raising."""
    config = {"steps": [{"step_type": "transformation"}]}
    result = _run(config)
    assert result["status"] == PIPELINE_ERROR_STATUS
    assert "operation" in result["error"]
    assert result["output_data"] == []
    assert result["steps_executed"] == []


def test_non_dict_step_returns_error() -> None:
    """A non-object step entry returns an error result rather than raising."""
    result = _run({"steps": ["not_a_step"]})
    assert result["status"] == PIPELINE_ERROR_STATUS
    assert "object" in result["error"]


def test_non_list_steps_returns_error() -> None:
    """A non-list 'steps' value returns an error result rather than raising."""
    result = _run({"steps": {"step_type": "transformation"}})
    assert result["status"] == PIPELINE_ERROR_STATUS
    assert "list" in result["error"]
