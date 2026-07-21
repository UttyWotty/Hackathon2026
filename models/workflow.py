"""
Workflow and project management models.

Includes:
  - Projects: high-level organizational unit
  - Tasks: actionable items (kanban-style status)
  - TaskTimer: time tracking sessions per task
  - Notes: lightweight knowledge base entries

Author: Utku Gulbardak
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from .database import Base


class Project(Base):
    """Project entity for grouping tasks/notes."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="active", nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Task(Base):
    """Task entity with optional project association."""

    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)  # UUID
    project_id = Column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )

    title = Column(String(300), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="todo", nullable=False, index=True)
    priority = Column(Integer, default=3, nullable=False, index=True)  # 1-5
    tags = Column(JSON, nullable=True)

    is_archived = Column(Boolean, default=False, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    total_tracked_seconds = Column(Integer, default=0, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "tags": self.tags or [],
            "is_archived": self.is_archived,
            "total_tracked_seconds": self.total_tracked_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class TaskTimer(Base):
    """Time tracking sessions for tasks."""

    __tablename__ = "task_timers"

    id = Column(String(36), primary_key=True)  # UUID
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    stopped_at = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Integer, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "duration_seconds": self.duration_seconds,
        }


class Note(Base):
    """Note entity for lightweight knowledge base."""

    __tablename__ = "notes"

    id = Column(String(36), primary_key=True)  # UUID
    project_id = Column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )

    title = Column(String(300), nullable=False, index=True)
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, *, include_content: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "tags": self.tags or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_content:
            data["content"] = self.content
        return data


def normalize_tags(tags: Optional[list[str]]) -> list[str]:
    """Normalize tags list for storage."""
    if not tags:
        return []
    return sorted({t.strip() for t in tags if t and t.strip()})
