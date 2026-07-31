"""
Tests for tool dispatcher - critical path for scheduler.

Tests:
- Tool registry pattern
- Async/sync tool handling
- Error handling
- Unknown tool fallback
"""

import asyncio

import pytest  # type: ignore[import-untyped]

from services.infrastructure.scheduler.tool_dispatcher import (
    _TOOL_IMPORTS,
    _TOOL_REGISTRY,
    _get_tool_function,
    dispatch_tool_direct,
)


def test_tool_registry_contains_all_tools():
    """Test that all expected tools are in the registry."""
    expected_tools = [
        "run_roi_analysis",
        "run_runrate_analysis",
        "run_rca_analysis",
        "run_ct_efficiency_analysis",
        "run_ct_deviation_analysis",
        "run_tooling_eol_analysis",
        "run_capacity_analysis",
        "refresh_master_shot_table",
    ]

    for tool_name in expected_tools:
        assert tool_name in _TOOL_IMPORTS, f"Tool {tool_name} should be in registry"


def test_get_tool_function_unknown():
    """Test that unknown tools raise ValueError."""
    with pytest.raises(ValueError, match="Unknown tool"):
        _get_tool_function("nonexistent_tool")


@pytest.mark.asyncio
async def test_dispatch_tool_direct_async_tool():
    """Test dispatching an async tool."""

    # Mock async tool function
    async def mock_async_tool(**kwargs):
        # Use async sleep to make it truly async
        await asyncio.sleep(0.001)
        return {"status": "success", "result": "test"}

    # Temporarily add to registry
    original_registry = _TOOL_REGISTRY.copy()
    _TOOL_REGISTRY["test_async_tool"] = mock_async_tool

    try:
        result = await dispatch_tool_direct("test_async_tool", {})
        assert result["status"] == "success"
    finally:
        _TOOL_REGISTRY.clear()
        _TOOL_REGISTRY.update(original_registry)


@pytest.mark.asyncio
async def test_dispatch_tool_direct_sync_tool():
    """Test dispatching a sync tool (should run in executor)."""

    # Mock sync tool function
    def mock_sync_tool(**kwargs):
        return {"status": "success", "result": "test"}

    # Temporarily add to registry
    original_registry = _TOOL_REGISTRY.copy()
    _TOOL_REGISTRY["test_sync_tool"] = mock_sync_tool

    try:
        result = await dispatch_tool_direct("test_sync_tool", {})
        assert result["status"] == "success"
    finally:
        _TOOL_REGISTRY.clear()
        _TOOL_REGISTRY.update(original_registry)


@pytest.mark.asyncio
async def test_dispatch_tool_direct_unknown_raises():
    """Test that unknown tools raise an error with status in the result."""
    result = await dispatch_tool_direct("unknown_tool", {})

    assert result is not None
    assert result.get("status") == "error"
    assert "unknown" in result.get("error", "").lower() or "Unknown" in result.get(
        "error", ""
    )


@pytest.mark.asyncio
async def test_dispatch_tool_direct_error_handling():
    """Test error handling in tool dispatch."""

    # Mock tool that raises exception
    def failing_tool(**kwargs):
        raise ValueError("Test error")

    original_registry = _TOOL_REGISTRY.copy()
    _TOOL_REGISTRY["failing_tool"] = failing_tool

    try:
        result = await dispatch_tool_direct("failing_tool", {})
        assert result["status"] == "error"
        assert "error" in result
    finally:
        _TOOL_REGISTRY.clear()
        _TOOL_REGISTRY.update(original_registry)
