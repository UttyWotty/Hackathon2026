"""
In-memory job store for tracking background pipeline executions.
Provides thread-safe job creation, updates, and retrieval for async pipeline runs.
Jobs are stored in a bounded dictionary with automatic eviction of oldest completed entries.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class JobStatus(str, Enum):
    """Possible states for a pipeline job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


MAX_STORED_JOBS = 100


@dataclass
class JobRecord:
    """Tracks the lifecycle of a single pipeline execution."""

    job_id: str
    pipeline_name: str
    mode: str
    schema_name: Optional[str]
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    message: Optional[str] = None
    execution_time_seconds: Optional[float] = None


_jobs: Dict[str, JobRecord] = {}
_lock = threading.Lock()


def create_job(
    pipeline_name: str,
    mode: str,
    schema_name: Optional[str] = None,
) -> JobRecord:
    """Create a new pending job and return it."""
    job_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()

    record = JobRecord(
        job_id=job_id,
        pipeline_name=pipeline_name,
        mode=mode,
        schema_name=schema_name,
        status=JobStatus.PENDING,
        created_at=now,
    )

    with _lock:
        _evict_if_full()
        _jobs[job_id] = record

    return record


def mark_running(job_id: str) -> None:
    """Transition a job to running state."""
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now().isoformat()


def mark_completed(
    job_id: str,
    success: bool,
    message: str,
    execution_time_seconds: float,
) -> None:
    """Transition a job to completed or failed state."""
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.status = JobStatus.COMPLETED if success else JobStatus.FAILED
            job.completed_at = datetime.now().isoformat()
            job.message = message
            job.execution_time_seconds = execution_time_seconds


def get_job(job_id: str) -> Optional[JobRecord]:
    """Retrieve a job by ID, or None if not found."""
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> List[JobRecord]:
    """Return all tracked jobs, newest first."""
    with _lock:
        return sorted(
            _jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )


def _evict_if_full() -> None:
    """Remove oldest completed/failed jobs when store exceeds MAX_STORED_JOBS."""
    if len(_jobs) < MAX_STORED_JOBS:
        return

    finished = sorted(
        [
            j
            for j in _jobs.values()
            if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ],
        key=lambda j: j.created_at,
    )

    while len(_jobs) >= MAX_STORED_JOBS and finished:
        oldest = finished.pop(0)
        _jobs.pop(oldest.job_id, None)
