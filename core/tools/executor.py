"""
Tool execution logic for MCP Protocol integration.

Provides execute_tool and execute_tool_async functions for routing tool calls
through the MCP Protocol endpoint with support for synchronous and async execution.
"""

import json
import logging
import os
import time
import traceback
from typing import Any, Dict

import requests  # type: ignore

from .email_sender import send_email_with_attachments

# API configuration
API_URL = os.getenv("API_BASE_URL", "http://localhost:3020")

# Common error messages
ERROR_UNKNOWN = "Unknown error"

logger = logging.getLogger(__name__)


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool using MCP Protocol endpoint.

    All tool calls now route through MCP Protocol endpoint (/tools/call) which:
    - Uses standard MCP protocol format
    - Automatically routes to the correct backend module
    - Returns results in MCP protocol format
    - Supports unified tool execution interface

    Args:
        tool_name: Name of the tool to execute (LLM tool name)
        tool_input: Input parameters for the tool

    Returns:
        dict: Tool execution results (parsed from MCP protocol response)
    """
    # Special handling for send_email_report (uses direct email function)
    if tool_name == "send_email_report":
        return send_email_with_attachments(
            recipient_email=tool_input.get("recipient_email"),
            file_paths=tool_input.get("file_paths", []),
            subject=tool_input.get("subject"),
            analysis_type=tool_input.get("analysis_type", "Analysis"),
            custom_body=tool_input.get("custom_body"),
        )

    # Call MCP Protocol endpoint
    try:
        mcp_url = f"{API_URL}/mcp/tools/call"

        # Format request in MCP protocol format
        mcp_request = {
            "name": tool_name,
            "arguments": tool_input,
        }

        # Make POST request to MCP protocol endpoint
        response = requests.post(mcp_url, json=mcp_request, timeout=300)
        response.raise_for_status()

        # Parse MCP protocol response
        mcp_response = response.json()

        # Check if there was an error
        if mcp_response.get("isError", False):
            # Extract error from MCP response
            error_text = mcp_response.get("content", [{}])[0].get("text", ERROR_UNKNOWN)
            try:
                error_data = json.loads(error_text)
                return {
                    "error": error_data.get("error", ERROR_UNKNOWN),
                    "status": "error",
                    "details": error_data,
                }
            except (json.JSONDecodeError, KeyError, IndexError):
                return {
                    "error": error_text,
                    "status": "error",
                }

        # Extract result from MCP response content
        content = mcp_response.get("content", [])
        if not content:
            return {
                "error": "Empty response from MCP protocol endpoint",
                "status": "error",
            }

        # Parse JSON from text content
        result_text = content[0].get("text", "{}")
        try:
            result = json.loads(result_text)
            return result
        except json.JSONDecodeError:
            # If JSON parsing fails, return the text as-is
            return {
                "status": "success",
                "message": "Tool executed successfully",
                "raw_response": result_text,
            }

    except requests.exceptions.Timeout:
        return {
            "error": f"Request timeout after 5 minutes for {tool_name}",
            "status": "error",
        }
    except requests.exceptions.ConnectionError:
        return {
            "error": f"Could not connect to API at {API_URL}. Is the server running? Start with: python main.py",
            "status": "error",
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": f"Request failed: {str(e)}",
            "status": "error",
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "status": "error",
        }


def execute_tool_async(
    tool_name: str,
    tool_input: Dict[str, Any],
    poll_interval: int = 2,
    max_wait: int = 300,
) -> Dict[str, Any]:
    """
    Execute a tool asynchronously with polling.

    Submits the tool for background execution and polls for results.
    This prevents UI blocking for long-running analyses.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        poll_interval: Seconds between status checks (default: 2)
        max_wait: Maximum seconds to wait (default: 300)

    Returns:
        dict: Tool execution results
    """
    # Special handling for send_email_report (not long-running)
    if tool_name == "send_email_report":
        return send_email_with_attachments(
            recipient_email=tool_input.get("recipient_email"),
            file_paths=tool_input.get("file_paths", []),
            subject=tool_input.get("subject"),
            analysis_type=tool_input.get("analysis_type", "Analysis"),
            custom_body=tool_input.get("custom_body"),
        )

    try:
        # Submit job for async execution
        submit_url = f"{API_URL}/mcp/tools/submit"
        submit_request = {
            "name": tool_name,
            "arguments": tool_input,
        }

        logger.info("Submitting async tool job: %s", tool_name)
        response = requests.post(submit_url, json=submit_request, timeout=10)
        response.raise_for_status()

        job_data = response.json()
        job_id = job_data.get("job_id")

        if not job_id:
            return {
                "error": "Failed to get job ID from server",
                "status": "error",
            }

        logger.info("Async job submitted: %s", job_id)
        logger.debug("Polling for async job results every %ss", poll_interval)

        # Poll for results
        start_time = time.time()
        status_url = f"{API_URL}/mcp/tools/jobs/{job_id}"

        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                return {
                    "error": f"Job timeout after {max_wait}s. Job ID: {job_id}. Use /tools/jobs/{job_id} to check status.",
                    "status": "error",
                    "job_id": job_id,
                }

            # Poll status
            time.sleep(poll_interval)
            status_response = requests.get(status_url, timeout=10)
            status_response.raise_for_status()

            job_status = status_response.json()
            status = job_status.get("status")
            progress = job_status.get("progress", 0)

            logger.debug(
                "Async job %s status=%s progress=%s elapsed=%ss",
                job_id,
                status,
                progress,
                int(elapsed),
            )

            if status == "completed":
                result = job_status.get("result", {})
                logger.info("Async job completed: %s", job_id)
                return result

            elif status == "failed":
                error = job_status.get("error", ERROR_UNKNOWN)
                logger.warning("Async job failed: %s error=%s", job_id, error)
                return {
                    "error": error,
                    "status": "error",
                    "job_id": job_id,
                }

    except requests.exceptions.Timeout:
        return {
            "error": "Request timeout for async job",
            "status": "error",
        }
    except requests.exceptions.ConnectionError:
        return {
            "error": f"Could not connect to API at {API_URL}. Is the server running?",
            "status": "error",
        }
    except Exception as e:
        return {
            "error": f"Async execution error: {str(e)}",
            "status": "error",
            "traceback": traceback.format_exc(),
        }
