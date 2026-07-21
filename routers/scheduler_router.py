"""
Scheduler Router - Job scheduling for automated analyses and reports.

Uses SQLite for persistent storage across server restarts.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import (  # type: ignore[import-untyped]  # type: ignore[import-untyped]
    BaseModel,
    Field,
)

from models.database import get_session
from models.scheduler import JobExecutionHistory, ScheduledJob
from services.infrastructure.scheduler.background_scheduler import _calculate_next_run
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()


# Request Models
class ScheduleJobRequest(BaseModel):
    name: str = Field(..., description="Descriptive job name")
    tool_name: str = Field(
        ...,
        description="Tool to execute (e.g., 'refresh_master_shot_table', 'run_roi_analysis')",
    )
    arguments: Optional[Dict[str, Any]] = Field(
        None, description="Arguments for the tool"
    )
    schedule: str = Field(
        ...,
        description="Schedule: cron ('0 2 * * *'), interval ('1h', '30m'), or 'once'",
    )
    enabled: bool = Field(True, description="Whether job is enabled")
    max_retries: int = Field(
        3, description="Maximum retry attempts on failure (default: 3)"
    )
    retry_backoff: int = Field(
        60,
        description="Base retry delay in seconds with exponential backoff (default: 60)",
    )


class UpdateJobRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable/disable job")
    schedule: Optional[str] = Field(None, description="Update schedule")
    arguments: Optional[Dict[str, Any]] = Field(None, description="Update arguments")


@router.get("/", summary="Scheduler Service Info")
async def scheduler_info():
    """Get information about the scheduler service."""
    try:
        with get_session() as session:
            total_jobs = session.query(ScheduledJob).count()
            active_jobs = (
                session.query(ScheduledJob).filter(ScheduledJob.enabled).count()
            )

        return {
            "service": "Scheduler Service",
            "description": "Schedule recurring jobs and automated tasks with persistent storage",
            "storage": "SQLite (persistent across restarts)",
            "total_jobs": total_jobs,
            "active_jobs": active_jobs,
            "schedule_formats": {
                "cron": "Standard cron format (e.g., '0 2 * * *' for daily at 2am)",
                "interval": "Human-readable intervals (e.g., '1h', '30m', '7d')",
                "once": "Execute once immediately or at specified time",
            },
        }
    except Exception as e:
        logger.error(f"Scheduler info error: {e}")
        return {
            "service": "Scheduler Service",
            "description": "Schedule recurring jobs and automated tasks",
            "error": "Database connection error",
        }


@router.post("/jobs", summary="Schedule a New Job")
async def schedule_job(request: ScheduleJobRequest):
    """
    Schedule a recurring or one-time job.

    Jobs are stored in SQLite and persist across server restarts.
    """
    try:
        with get_session() as session:
            job_id = str(uuid.uuid4())
            next_run = _calculate_next_run(request.schedule)

            job = ScheduledJob(
                id=job_id,
                name=request.name,
                tool_name=request.tool_name,
                arguments=request.arguments or {},
                schedule=request.schedule,
                enabled=request.enabled,
                next_run=next_run,
                status="scheduled" if request.enabled else "disabled",
                max_retries=request.max_retries,
                retry_backoff=request.retry_backoff,
                retry_count=0,
            )

            session.add(job)
            session.commit()

            result = job.to_dict()

        return {
            "status": "success",
            "message": f"Job '{request.name}' scheduled successfully and persisted to database",
            "job": result,
        }

    except Exception as e:
        logger.error(f"Schedule job error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/jobs", summary="List All Scheduled Jobs")
async def list_jobs(enabled_only: bool = False):
    """
    List all scheduled jobs from database.

    Jobs persist across server restarts.
    """
    try:
        with get_session() as session:
            query = session.query(ScheduledJob)
            if enabled_only:
                query = query.filter(ScheduledJob.enabled)

            jobs = query.order_by(ScheduledJob.next_run).all()
            result_jobs = [job.to_dict() for job in jobs]

        return {
            "status": "success",
            "total_jobs": len(result_jobs),
            "jobs": result_jobs,
        }

    except Exception as e:
        logger.error(f"List jobs error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/jobs/{job_id}", summary="Get Job Details")
async def get_job(job_id: str):
    """Get detailed information about a specific job from database."""
    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

            result = job.to_dict()

        return {
            "status": "success",
            "job": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get job error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.patch("/jobs/{job_id}", summary="Update Job")
async def update_job(job_id: str, request: UpdateJobRequest):
    """Update job configuration in database (persists across restarts)."""
    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

            if request.enabled is not None:
                job.enabled = request.enabled
                job.status = "scheduled" if request.enabled else "disabled"

            if request.schedule is not None:
                job.schedule = request.schedule
                job.next_run = _calculate_next_run(request.schedule)

            if request.arguments is not None:
                job.arguments = request.arguments

            job.updated_at = datetime.now()

            session.commit()
            result = job.to_dict()

        return {
            "status": "success",
            "message": f"Job '{job_id}' updated successfully in database",
            "job": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update job error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.delete("/jobs/{job_id}", summary="Delete Job")
async def delete_job(job_id: str):
    """Delete a scheduled job from database permanently."""
    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

            job_name = job.name
            session.delete(job)
            session.commit()

        return {
            "status": "success",
            "message": f"Job '{job_name}' deleted permanently from database",
            "job_id": job_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete job error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/jobs/{job_id}/trigger", summary="Trigger Job Manually")
async def trigger_job(job_id: str):
    """
    Trigger a job to run immediately (outside its schedule).

    Updates run count and last_run timestamp in database.
    """
    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

            # Update job state
            job.last_run = datetime.now()
            job.run_count = (job.run_count or 0) + 1
            job.status = "running"

            session.commit()

        return {
            "status": "success",
            "message": f"Job '{job.name}' triggered manually",
            "job_id": job_id,
            "run_count": job.run_count,
            "note": "Job execution would happen here in production (requires task queue like Celery)",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trigger job error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/jobs/{job_id}/enable", summary="Enable Job")
async def enable_job(job_id: str):
    """Enable a disabled job in database."""
    return await update_job(job_id, UpdateJobRequest(enabled=True))


@router.post("/jobs/{job_id}/disable", summary="Disable Job")
async def disable_job(job_id: str):
    """Disable a scheduled job."""
    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

            job.enabled = False
            session.commit()

        return {"status": "success", "message": f"Job '{job.name}' disabled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling job: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Failed to disable job.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/jobs/{job_id}/history", summary="Get Job Execution History")
async def get_job_history(job_id: str, limit: int = 50):
    """Get execution history for a specific job."""
    try:
        with get_session() as session:
            # Verify job exists
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

            # Get execution history
            history = (
                session.query(JobExecutionHistory)
                .filter(JobExecutionHistory.job_id == job_id)
                .order_by(JobExecutionHistory.started_at.desc())
                .limit(limit)
                .all()
            )

        return {
            "status": "success",
            "job_id": job_id,
            "job_name": job.name,
            "count": len(history),
            "history": [execution.to_dict() for execution in history],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job history: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Failed to get job history.")
        raise HTTPException(status_code=500, detail=error_msg)
