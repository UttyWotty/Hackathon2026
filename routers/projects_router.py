"""
Projects Router.

Projects are high-level organizational units for tasks and notes.

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from models.database import get_session
from models.workflow import Project

logger = logging.getLogger(__name__)
router = APIRouter()


class ProjectCreateRequest(BaseModel):
    """Create project payload."""

    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    """Update project payload."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, description="active|archived|completed")


@router.get("/", summary="List Projects")
async def list_projects():
    """List projects."""
    with get_session() as session:
        projects = session.query(Project).order_by(Project.created_at.desc()).all()
        return {
            "status": "success",
            "count": len(projects),
            "projects": [p.to_dict() for p in projects],
        }


@router.post("/", summary="Create Project")
async def create_project(request: ProjectCreateRequest):
    """Create a new project."""
    with get_session() as session:
        existing = session.query(Project).filter(Project.name == request.name).first()
        if existing:
            raise HTTPException(status_code=409, detail="Project already exists")

        project = Project(
            id=str(uuid4()),
            name=request.name.strip(),
            description=request.description,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(project)
        session.flush()
        return {"status": "success", "project": project.to_dict()}


@router.patch("/{project_id}", summary="Update Project")
async def update_project(project_id: str, request: ProjectUpdateRequest):
    """Update an existing project."""
    with get_session() as session:
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if request.name is not None:
            project.name = request.name.strip()
        if request.description is not None:
            project.description = request.description
        if request.status is not None:
            project.status = request.status
        project.updated_at = datetime.utcnow()
        session.add(project)
        return {"status": "success", "project": project.to_dict()}


@router.delete("/{project_id}", summary="Delete Project")
async def delete_project(project_id: str):
    """Delete a project."""
    with get_session() as session:
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        session.delete(project)
        return {"status": "success", "message": "Project deleted"}
