"""
Tasks Router.

Provides basic task tracking (kanban-style) and time tracking via timers.

Key endpoints:
  - GET/POST /tasks/
  - PATCH /tasks/{task_id}/status
  - POST /tasks/{task_id}/timer?action=start|stop

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from models.database import get_session
from models.workflow import Task, TaskTimer, normalize_tags
from services.infrastructure.audit.sqlite_logger import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter()


class TaskCreateRequest(BaseModel):
    """Create task payload."""

    title: str = Field(..., min_length=2, max_length=300)
    description: Optional[str] = None
    project_id: Optional[str] = None
    priority: int = Field(3, ge=1, le=5)
    tags: Optional[List[str]] = None


class TaskStatusUpdateRequest(BaseModel):
    """Update status payload."""

    status: str = Field(..., description="todo|in_progress|blocked|done")


@router.get("/", summary="List Tasks")
async def list_tasks(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    include_archived: bool = Query(False),
):
    """List tasks, optionally filtered."""
    with get_session() as session:
        q = session.query(Task)
        if project_id:
            q = q.filter(Task.project_id == project_id)
        if status:
            q = q.filter(Task.status == status)
        if not include_archived:
            q = q.filter(Task.is_archived == False)  # noqa: E712
        tasks = q.order_by(Task.created_at.desc()).all()
        return {
            "status": "success",
            "count": len(tasks),
            "tasks": [t.to_dict() for t in tasks],
        }


@router.post("/", summary="Create Task")
async def create_task(request: TaskCreateRequest):
    """Create a task."""
    with get_session() as session:
        task = Task(
            id=str(uuid4()),
            project_id=request.project_id,
            title=request.title.strip(),
            description=request.description,
            status="todo",
            priority=request.priority,
            tags=normalize_tags(request.tags),
            is_archived=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_tracked_seconds=0,
        )
        session.add(task)
        session.flush()
        return {"status": "success", "task": task.to_dict()}


@router.patch("/{task_id}/status", summary="Update Task Status")
async def update_task_status(task_id: str, request: TaskStatusUpdateRequest):
    """Update task status."""
    with get_session() as session:
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        task.status = request.status
        task.updated_at = datetime.utcnow()
        if request.status == "done":
            task.completed_at = datetime.utcnow()
        session.add(task)
        return {"status": "success", "task": task.to_dict()}


@router.post("/{task_id}/timer", summary="Task Timer Control")
async def task_timer(
    task_id: str,
    action: str = Query(
        "start",
        description="Timer action: start|stop",
        pattern="^(start|stop)$",
    ),
):
    """
    Start/stop a timer for a task.

    Behavior:
      - start: creates a new TaskTimer with stopped_at NULL
      - stop: closes the most recent open timer, updates task.total_tracked_seconds
    """
    with get_session() as session:
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if action == "start":
            timer = TaskTimer(
                id=str(uuid4()),
                task_id=task_id,
                started_at=datetime.utcnow(),
                stopped_at=None,
                duration_seconds=None,
            )
            session.add(timer)
            session.flush()

            # Audit hook (best-effort)
            try:
                log_audit_event(
                    service="tasks",
                    tool_name="timer_start",
                    user_id=None,
                    status="success",
                    metadata={"task_id": task_id},
                )
            except Exception:
                logger.debug("Audit logging failed for timer_start", exc_info=True)

            return {"status": "success", "timer": timer.to_dict()}

        # stop
        timer = (
            session.query(TaskTimer)
            .filter(TaskTimer.task_id == task_id, TaskTimer.stopped_at.is_(None))
            .order_by(TaskTimer.started_at.desc())
            .first()
        )
        if not timer:
            raise HTTPException(status_code=409, detail="No active timer to stop")

        timer.stopped_at = datetime.utcnow()
        duration = int((timer.stopped_at - timer.started_at).total_seconds())
        timer.duration_seconds = max(duration, 0)
        session.add(timer)

        task.total_tracked_seconds = (
            int(task.total_tracked_seconds or 0) + timer.duration_seconds
        )
        task.updated_at = datetime.utcnow()
        session.add(task)

        try:
            log_audit_event(
                service="tasks",
                tool_name="timer_stop",
                user_id=None,
                status="success",
                metadata={
                    "task_id": task_id,
                    "duration_seconds": timer.duration_seconds,
                },
            )
        except Exception:
            logger.debug("Audit logging failed for timer_stop", exc_info=True)

        return {"status": "success", "timer": timer.to_dict(), "task": task.to_dict()}
