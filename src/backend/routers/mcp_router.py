"""MCP Protocol Router - Model Context Protocol Support for LLM Integration.

Provides MCP protocol endpoints including root discovery, tool listing, tool execution,
multi-step reasoning chains, REST API tool discovery, and metadata endpoints. Delegates
tool utility functions to mcp_tool_utils and async job management to mcp_jobs_router.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import (  # type: ignore[import-untyped]
    APIRouter,
    Body,
    HTTPException,
    Query,
    Request,
    status,
)

from routers.mcp_jobs_router import jobs_router
from routers.mcp_tool_utils import filter_tools_by_tags, get_all_tags, get_mcp_tools
from services.infrastructure.scheduler.tool_dispatcher import dispatch_tool_direct

logger = logging.getLogger(__name__)

router = APIRouter()

# Include the async job management sub-router
router.include_router(jobs_router)


# ============================================================================
# Root MCP Endpoints (Standard MCP Protocol)
# ============================================================================


@router.get("", tags=["MCP Protocol"], summary="MCP Server Info (Root)")
@router.get("/", tags=["MCP Protocol"], summary="MCP Server Info (Root)")
async def mcp_root_get() -> Dict[str, Any]:
    """Root MCP endpoint - returns server information.

    Standard MCP protocol discovery endpoint.
    """
    tools = get_mcp_tools()
    return {
        "name": "Manufacturing Analytics MCP Server",
        "version": "2.0.0",
        "protocol": "mcp",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
        },
        "tools_count": len(tools),
        "endpoints": {
            "list_tools": "POST /mcp/tools/list",
            "call_tool": "POST /mcp/tools/call",
            "info": "GET /mcp/info",
        },
    }


@router.post("", tags=["MCP Protocol"], summary="MCP Protocol Handler (Root)")
@router.post("/", tags=["MCP Protocol"], summary="MCP Protocol Handler (Root)")
async def mcp_root_post(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Root MCP protocol handler.

    Routes MCP protocol requests based on the 'method' field.
    Supports standard MCP protocol methods:
    - tools/list: List available tools
    - tools/call: Execute a tool
    - initialize: MCP initialization handshake
    """
    method = body.get("method", "")

    if method == "tools/list":
        return _handle_tools_list()

    elif method == "tools/call":
        return await _handle_tools_call(body)

    elif method == "initialize":
        return _handle_initialize()

    else:
        return {
            "error": {
                "code": -32601,
                "message": f"Unknown method: {method}. Supported: tools/list, tools/call, initialize",
            }
        }


def _handle_tools_list() -> Dict[str, Any]:
    """Handle the tools/list MCP method."""
    tools = get_mcp_tools()
    return {"tools": tools}


async def _handle_tools_call(body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle the tools/call MCP method."""
    params = body.get("params", {})
    tool_name = params.get("name") or params.get("tool")
    arguments = params.get("arguments") or params.get("args") or {}

    if not tool_name:
        return {
            "error": {"code": -32602, "message": "Tool name is required"},
            "isError": True,
        }

    try:
        result = await dispatch_tool_direct(tool_name, arguments)
        is_error = result.get("status") == "error" or "error" in result
        return {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "isError": is_error,
        }
    except Exception as e:
        return {
            "error": {"code": -32603, "message": str(e)},
            "isError": True,
        }


def _handle_initialize() -> Dict[str, Any]:
    """Handle the initialize MCP method (handshake)."""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "Manufacturing Analytics MCP Server",
            "version": "2.0.0",
        },
    }


@router.post(
    "/tools/reason",
    tags=["MCP Protocol"],
    summary="Execute Multi-step Tool Plan (Reasoning Chain)",
)
async def reason_tools(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Execute a sequential multi-step tool plan for agent-style orchestration.

    Non-transactional: if a step fails when stop_on_error is true, partial results
    are returned. Body expects {"steps": [...], "stop_on_error": true}.
    """
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        raise HTTPException(status_code=400, detail="steps must be a non-empty list")
    if not all(isinstance(step, dict) for step in steps):
        raise HTTPException(
            status_code=400,
            detail="each step must be an object with a tool name and arguments",
        )

    stop_on_error = bool(body.get("stop_on_error", True))
    results: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps):
        step_result = await _execute_reason_step(idx, step, stop_on_error, results)
        if step_result is False:
            break

    return {
        "status": "success",
        "count": len(results),
        "stop_on_error": stop_on_error,
        "steps": results,
    }


async def _execute_reason_step(
    idx: int,
    step: Dict[str, Any],
    stop_on_error: bool,
    results: List[Dict[str, Any]],
) -> bool:
    """Execute a single step in a reasoning chain. Returns False to stop."""
    tool_name = step.get("name") or step.get("tool")
    arguments = step.get("arguments") or step.get("args") or {}
    if not tool_name:
        raise HTTPException(status_code=400, detail=f"Step {idx} missing tool name")
    try:
        logger.info("MCP tool plan step %s: %s", idx + 1, tool_name)
        step_result = await dispatch_tool_direct(tool_name, arguments)
        results.append(
            {
                "step": idx + 1,
                "tool": tool_name,
                "arguments": arguments,
                "result": step_result,
            }
        )
        if stop_on_error and (
            step_result.get("status") == "error" or "error" in step_result
        ):
            return False
    except Exception as e:
        logger.error("Tool plan step failed: %s", e, exc_info=True)
        results.append(
            {
                "step": idx + 1,
                "tool": tool_name,
                "arguments": arguments,
                "result": {"status": "error", "error": str(e)},
            }
        )
        if stop_on_error:
            return False

    return True


# ============================================================================
# Tool Discovery Endpoints
# ============================================================================


@router.post("/tools/list", tags=["MCP Protocol"], summary="List Available Tools")
async def list_tools(
    request: Request,
    body: Optional[Dict[str, Any]] = Body(None),
) -> Dict[str, Any]:
    """MCP protocol endpoint for tool discovery with optional tag filtering.

    Returns tools in MCP format. Body may include tags, server, domain,
    operation, and exclude_tags fields for filtering.
    """
    try:
        tools = get_mcp_tools()

        if body:
            tools = _apply_body_filters(tools, body)

        return {
            "tools": tools,
            "count": len(tools),
        }
    except Exception as e:
        logger.error("Error listing tools: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tools: {str(e)}",
        )


def _apply_body_filters(
    tools: List[Dict[str, Any]], body: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Apply tag filters from a request body to a tool list.

    Args:
        tools: List of MCP tools
        body: Request body with optional filter keys

    Returns:
        Filtered list of tools
    """
    tags = body.get("tags")
    server = body.get("server")
    domain = body.get("domain")
    operation = body.get("operation")
    exclude_tags = body.get("exclude_tags")

    if tags or server or domain or operation or exclude_tags:
        tools = filter_tools_by_tags(
            tools,
            tags=tags,
            server=server,
            domain=domain,
            operation=operation,
            exclude_tags=exclude_tags,
        )

    return tools


@router.post("/tools/call", tags=["MCP Protocol"], summary="Call Tool via MCP Protocol")
async def call_tool(
    request: Request,
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Execute a tool via MCP protocol format.

    Accepts name/tool and arguments/args fields. Returns MCP content response.
    """
    try:
        tool_name = body.get("name") or body.get("tool")
        if not tool_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tool name is required. Provide 'name' or 'tool' field.",
            )

        arguments = body.get("arguments") or body.get("args") or {}

        logger.info("MCP tool call: %s with args: %s", tool_name, arguments)
        result = await dispatch_tool_direct(tool_name, arguments)

        return _format_tool_result(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error executing MCP tool call: %s", e, exc_info=True)
        error_response = {
            "error": str(e),
            "status": "error",
            "tool_name": tool_name if "tool_name" in locals() else "unknown",
        }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(error_response, indent=2),
                }
            ],
            "isError": True,
        }


def _format_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Format a tool execution result as an MCP protocol response.

    Args:
        result: Raw tool execution result

    Returns:
        MCP-formatted response with content and isError fields
    """
    is_error = result.get("status") == "error" or "error" in result

    if is_error:
        error_message = result.get("error", "Unknown error occurred")
        error_text = json.dumps(
            {
                "error": error_message,
                "status": "error",
                "details": result,
            },
            indent=2,
        )
        return {
            "content": [{"type": "text", "text": error_text}],
            "isError": True,
        }

    result_text = json.dumps(result, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": result_text}],
        "isError": False,
    }


@router.get("/mcp/tools", tags=["MCP Protocol"], summary="List Tools (REST API)")
async def get_tools_rest(
    tags: Optional[List[str]] = Query(
        None, description="Filter by tag values (searches all tag dimensions)"
    ),
    server: Optional[str] = Query(None, description="Filter by server tag"),
    domain: Optional[str] = Query(None, description="Filter by domain tag"),
    operation: Optional[str] = Query(None, description="Filter by operation tag"),
    exclude_tags: Optional[List[str]] = Query(
        None, description="Exclude tools with these tags"
    ),
) -> Dict[str, Any]:
    """REST API endpoint for tool discovery with query-parameter-based tag filtering."""
    try:
        tools = get_mcp_tools()
        original_count = len(tools)

        filtered_tools = filter_tools_by_tags(
            tools,
            tags=tags,
            server=server,
            domain=domain,
            operation=operation,
            exclude_tags=exclude_tags,
        )

        return {
            "tools": filtered_tools,
            "count": len(filtered_tools),
            "total_count": original_count,
            "filters_applied": {
                "tags": tags,
                "server": server,
                "domain": domain,
                "operation": operation,
                "exclude_tags": exclude_tags,
            },
        }
    except Exception as e:
        logger.error("Error getting tools: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tools: {str(e)}",
        )


# ============================================================================
# Metadata Endpoints
# ============================================================================


@router.get(
    "/mcp/tools/by-server", tags=["MCP Protocol"], summary="Group Tools by Server"
)
async def get_tools_by_server() -> Dict[str, Any]:
    """Group tools by server/domain.

    Returns tools organized by server tag for easier navigation.
    """
    try:
        tools = get_mcp_tools()
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for tool in tools:
            server = tool.get("tags", {}).get("server", "other")
            if server not in grouped:
                grouped[server] = []
            grouped[server].append(tool)

        result: Dict[str, Any] = {}
        for server_name, server_tools in grouped.items():
            result[server_name] = {
                "tools": server_tools,
                "count": len(server_tools),
            }

        return result
    except Exception as e:
        logger.error("Error grouping tools: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to group tools: {str(e)}",
        )


@router.get("/mcp/tools/tags", tags=["MCP Protocol"], summary="List All Tags")
async def list_all_tags() -> Dict[str, List[str]]:
    """List all available tags across all dimensions.

    Returns all unique tag values organized by dimension.
    """
    try:
        tools = get_mcp_tools()
        all_tags = get_all_tags(tools)
        return all_tags
    except Exception as e:
        logger.error("Error listing tags: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tags: {str(e)}",
        )


@router.get("/mcp/info", tags=["MCP Protocol"], summary="MCP Server Information")
async def mcp_info() -> Dict[str, Any]:
    """Get MCP server information and capabilities."""
    tools = get_mcp_tools()
    all_tags = get_all_tags(tools)

    return {
        "name": "Manufacturing Analytics MCP Server",
        "version": "2.0.0",
        "protocol": "mcp",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
            "async_jobs": True,
        },
        "tools_count": len(tools),
        "tag_support": True,
        "available_tags": all_tags,
        "endpoints": {
            "list_tools": "/tools/list (POST)",
            "get_tools": "/mcp/tools (GET)",
            "call_tool": "/tools/call",
            "submit_job": "/tools/submit (POST)",
            "job_status": "/tools/jobs/{job_id} (GET)",
            "list_jobs": "/tools/jobs (GET)",
            "by_server": "/mcp/tools/by-server",
            "tags": "/mcp/tools/tags",
            "info": "/mcp/info",
        },
    }
