"""
Job result handling, monitoring, and audit logging for scheduled job executions.

This module contains the post-execution logic extracted from the background scheduler,
including success/failure handling, retry scheduling, result summarization, audit
logging, and metrics recording. All functions operate on ORM model instances or
primitive values passed in from the scheduler.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Constants
UNKNOWN_ERROR = "Unknown error"
MAX_ERROR_LENGTH = 500
MAX_RESULT_LENGTH = 1000
AUDIT_TIMEOUT_SECONDS = 2.0


def handle_job_success(
    job: Any,
    history_record: Any,
    result: Optional[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    execution_time_ms: int,
) -> None:
    """
    Handle successful job execution by updating job and history record state.

    Resets error tracking, increments run count, stores result summary,
    and calculates the next scheduled run time.

    Args:
        job: ScheduledJob ORM instance (already in a session).
        history_record: JobExecutionHistory ORM instance (already in a session).
        result: Tool execution result dictionary, or None.
        start_time: When execution started.
        end_time: When execution finished.
        execution_time_ms: Wall-clock execution duration in milliseconds.
    """
    from services.infrastructure.scheduler.background_scheduler import (
        _calculate_next_run,
    )

    job.run_count = (job.run_count or 0) + 1
    job.status = "scheduled"
    job.error_count = 0
    job.last_error = None
    job.retry_count = 0
    logger.info("Job completed successfully: %s", job.name)

    if result:
        job.last_result = json.dumps(result, default=str)[:MAX_RESULT_LENGTH]

    history_record.status = "success"
    history_record.completed_at = end_time
    history_record.execution_time_ms = execution_time_ms
    history_record.result_data = result
    history_record.result_summary = generate_result_summary(result)

    if job.schedule != "once":
        job.next_run = _calculate_next_run(job.schedule, start_time)
    else:
        job.enabled = False
        job.status = "completed"
        logger.info("One-time job completed, disabled: %s", job.name)


def handle_job_failure(
    job: Any,
    history_record: Any,
    error_message: Optional[str],
    result: Optional[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    execution_time_ms: int,
) -> None:
    """
    Handle failed job execution with retry logic and alerting.

    Increments error counts, schedules retries with exponential backoff,
    and sends a Google Chat alert when max retries are exceeded.

    Args:
        job: ScheduledJob ORM instance (already in a session).
        history_record: JobExecutionHistory ORM instance (already in a session).
        error_message: Human-readable error description, or None.
        result: Tool execution result dictionary, or None.
        start_time: When execution started.
        end_time: When execution finished.
        execution_time_ms: Wall-clock execution duration in milliseconds.
    """

    job.error_count = (job.error_count or 0) + 1
    job.last_error = (
        error_message[:MAX_ERROR_LENGTH] if error_message else UNKNOWN_ERROR
    )
    job.retry_count = (job.retry_count or 0) + 1

    max_retries = job.max_retries or 3

    if job.retry_count < max_retries:
        _schedule_retry(job, error_message, max_retries, start_time)
    else:
        _handle_max_retries_exceeded(job, error_message, max_retries, start_time)

    if result:
        job.last_result = json.dumps(result, default=str)[:MAX_RESULT_LENGTH]

    history_record.status = "error"
    history_record.completed_at = end_time
    history_record.execution_time_ms = execution_time_ms
    history_record.error_message = error_message
    history_record.result_data = result
    history_record.result_summary = "Error: %s" % error_message


def _schedule_retry(
    job: Any,
    error_message: Optional[str],
    max_retries: int,
    start_time: datetime,
) -> None:
    """
    Schedule a retry for a failed job with exponential backoff.

    Args:
        job: ScheduledJob ORM instance.
        error_message: Error description for logging.
        max_retries: Maximum allowed retries for this job.
        start_time: Original execution start time.
    """
    retry_delay_seconds = job.retry_backoff * (2 ** (job.retry_count - 1))
    retry_time = start_time + timedelta(seconds=retry_delay_seconds)
    job.next_run = retry_time
    job.status = "retrying"
    logger.warning(
        "Job failed, scheduling retry %d/%d in %ds: %s - %s",
        job.retry_count,
        max_retries,
        retry_delay_seconds,
        job.name,
        error_message,
    )


def _handle_max_retries_exceeded(
    job: Any,
    error_message: Optional[str],
    max_retries: int,
    start_time: datetime,
) -> None:
    """
    Handle a job that has exceeded its maximum retry count.

    Sets the job to error state, sends a Google Chat alert, and
    schedules the next regular run if the job is recurring.

    Args:
        job: ScheduledJob ORM instance.
        error_message: Error description for alerting and logging.
        max_retries: The maximum retries that were exceeded.
        start_time: Original execution start time.
    """
    from services.infrastructure.scheduler.background_scheduler import (
        _calculate_next_run,
    )

    job.status = "error"
    job.retry_count = 0
    logger.error(
        "Job failed after %d retries: %s - %s",
        max_retries,
        job.name,
        error_message,
    )

    _send_failure_alert(job, error_message, max_retries)

    if job.schedule != "once":
        job.next_run = _calculate_next_run(job.schedule, start_time)
    else:
        job.enabled = False
        job.status = "failed"


def _send_failure_alert(
    job: Any,
    error_message: Optional[str],
    max_retries: int,
) -> None:
    """
    Send a Google Chat webhook alert for a permanently failed job.

    Args:
        job: ScheduledJob ORM instance.
        error_message: Error description to include in the alert.
        max_retries: Number of retries that were attempted.
    """
    from services.infrastructure.google_chat.alert_sender import (
        send_alert as send_chat_alert,
    )

    alert_error_max_length = 300
    send_chat_alert(
        title="Scheduler Job Failed: %s" % job.name,
        message=(
            "Job '%s' failed after %d retries.\n\nError: %s"
            % (job.name, max_retries, error_message)
        ),
        severity="critical",
        source="scheduler",
        alert_key="scheduler:%s" % job.name,
        extra_fields={
            "Job Name": job.name,
            "Tool": getattr(job, "tool_name", "N/A"),
            "Max Retries": str(max_retries),
            "Last Error": str(error_message)[:alert_error_max_length],
        },
    )


def handle_job_execution_error(job_id: str, error: Exception) -> None:
    """
    Handle fatal errors during job execution by marking the job as errored.

    This is called when the entire execution wrapper fails, not just the tool.

    Args:
        job_id: The ID of the job that encountered a fatal error.
        error: The exception that was raised.
    """
    from models.database import get_session
    from models.scheduler import ScheduledJob

    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if job:
                job.status = "error"
                job.error_count = (job.error_count or 0) + 1
                job.last_error = str(error)[:MAX_ERROR_LENGTH]
                session.commit()
    except Exception as db_error:
        logger.warning("Failed to update job error status: %s", db_error)


def generate_result_summary(result: Optional[Dict[str, Any]]) -> str:
    """
    Generate a human-readable summary from a tool execution result.

    Extracts status, key metrics, and output file information into a
    concise single-line summary string.

    Args:
        result: Tool execution result dictionary, or None.

    Returns:
        A human-readable summary string.
    """
    if not result:
        return "No result data"

    status = result.get("status", "unknown")

    if status == "success":
        return _build_success_summary(result)

    error = result.get("error", UNKNOWN_ERROR)
    return "Error: %s" % error


def _build_success_summary(result: Dict[str, Any]) -> str:
    """
    Build a summary string for a successful result.

    Args:
        result: Tool execution result dictionary with status == "success".

    Returns:
        A pipe-delimited summary of key information.
    """
    summary_parts = ["Success"]

    if "metrics" in result:
        metrics = result["metrics"]
        if isinstance(metrics, dict):
            metric_keys = [
                "total_shots",
                "efficiency_percentage",
                "total_sessions",
            ]
            key_metrics = [
                "%s: %s" % (key, metrics[key]) for key in metric_keys if key in metrics
            ]
            if key_metrics:
                summary_parts.append(" | ".join(key_metrics))

    if "output_files" in result:
        output_files = result["output_files"]
        if isinstance(output_files, dict) and "filename" in output_files:
            summary_parts.append("File: %s" % output_files["filename"])

    return " | ".join(summary_parts)


async def log_job_execution(
    job_id: str,
    job_name: str,
    tool_name: str,
    success: bool,
    error_message: Optional[str],
    start_time: datetime,
) -> None:
    """
    Log job execution to the audit system using an async HTTP client.

    Failures are silently logged at DEBUG level so they do not interfere
    with job execution flow.

    Args:
        job_id: Job ID.
        job_name: Human-readable job name.
        tool_name: Name of the tool that was executed.
        success: Whether execution succeeded.
        error_message: Error message if execution failed, or None.
        start_time: When execution started (used to compute duration).
    """
    try:
        import httpx  # type: ignore[import-untyped]

        execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        audit_data = {
            "service": "scheduler",
            "tool_name": tool_name,
            "status": "success" if success else "error",
            "execution_time_ms": execution_time_ms,
            "error_message": error_message,
            "extra_data": {
                "job_id": job_id,
                "job_name": job_name,
                "scheduled_execution": True,
            },
        }

        try:
            from utils.error_handling import get_api_base_url

            api_url = get_api_base_url()
            async with httpx.AsyncClient(timeout=AUDIT_TIMEOUT_SECONDS) as client:
                await client.post("%s/audit/log" % api_url, json=audit_data)
        except (httpx.RequestError, httpx.TimeoutException) as req_err:
            logger.debug("Audit logging request failed: %s", req_err)

    except Exception as exc:
        logger.debug("Audit logging error: %s", exc)
