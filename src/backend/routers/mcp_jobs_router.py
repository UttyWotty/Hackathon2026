"""MCP Async Job Management Router - Endpoints for submitting and tracking async tool jobs.

Provides a FastAPI sub-router with endpoints for non-blocking tool execution: submit a
tool for background processing, poll for job status, and list recent jobs. Jobs are
managed via the shared job queue with automatic 24-hour cleanup.
"""

import logging
from typing import Any, Dict

from fastapi import (  # type: ignore[import-untyped]
    APIRouter,
    Body,
    HTTPException,
    Query,
    Request,
    status,
)

from services.infrastructure.jobs.job_queue import get_job_queue

logger = logging.getLogger(__name__)

jobs_router = APIRouter()


async def _execute_tool_async(
    tool_name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """Async wrapper for tool execution via the tool dispatcher.

    Routes tool execution through the scheduler's dispatch layer so that
    long-running tools do not block the request thread.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments dictionary

    Returns:
        Tool execution result dictionary
    """
    from services.infrastructure.scheduler.tool_dispatcher import dispatch_tool_direct

    try:
        result = await dispatch_tool_direct(tool_name, arguments)
        return result

    except Exception as e:
        logger.error("Error executing tool %s: %s", tool_name, e, exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


@jobs_router.post(
    "/tools/submit",
    tags=["MCP Protocol", "Async Jobs"],
    summary="Submit Tool for Async Execution",
)
async def submit_job(
    request: Request,
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Submit a tool for asynchronous execution (non-blocking).

    Use this endpoint for long-running analyses that would otherwise timeout.
    Returns immediately with a job_id that can be used to poll for status.

    Request body:
        {
            "name": "tool_name",    # Required: Tool name
            "arguments": {...},     # Required: Tool arguments
            "async": true           # Optional: Force async execution
        }

    Returns:
        {
            "job_id": "uuid",
            "status": "pending",
            "message": "Job submitted successfully",
            "poll_url": "/tools/jobs/{job_id}"
        }
    """
    try:
        tool_name = body.get("name") or body.get("tool")
        if not tool_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tool name is required. Provide 'name' or 'tool' field.",
            )

        arguments = body.get("arguments") or body.get("args") or {}

        job_queue = get_job_queue()
        job_id = await job_queue.submit_job(
            tool_name=tool_name,
            arguments=arguments,
            executor_func=_execute_tool_async,
        )

        logger.info("Async job submitted: %s (%s)", job_id, tool_name)

        return {
            "job_id": job_id,
            "status": "pending",
            "message": "Job submitted successfully",
            "poll_url": f"/tools/jobs/{job_id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error submitting job: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit job: {str(e)}",
        )


@jobs_router.get(
    "/tools/jobs/{job_id}",
    tags=["MCP Protocol", "Async Jobs"],
    summary="Get Job Status",
)
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get the status and result of an async job.

    Poll this endpoint to check if a job has completed.

    Returns:
        {
            "job_id": "uuid",
            "status": "pending"|"running"|"completed"|"failed",
            "result": {...},         # Only present if status is "completed"
            "error": "...",          # Only present if status is "failed"
            "progress": 0-100,
            "created_at": "ISO datetime",
            "started_at": "ISO datetime",
            "completed_at": "ISO datetime"
        }
    """
    try:
        job_queue = get_job_queue()
        job_status = await job_queue.get_job_status(job_id)

        if not job_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )

        return job_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting job status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )


@jobs_router.get(
    "/tools/jobs", tags=["MCP Protocol", "Async Jobs"], summary="List Recent Jobs"
)
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """List recent jobs.

    Returns a list of recent jobs with their status.

    Query parameters:
        - limit: Maximum number of jobs to return (default: 50, max: 200)

    Returns:
        {
            "jobs": [
                {
                    "job_id": "uuid",
                    "tool_name": "...",
                    "status": "...",
                    ...
                }
            ],
            "count": <number>
        }
    """
    try:
        job_queue = get_job_queue()
        jobs = await job_queue.list_jobs(limit=limit)

        return {
            "jobs": jobs,
            "count": len(jobs),
        }

    except Exception as e:
        logger.error("Error listing jobs: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}",
        )
