"""
Notes Router.

Notes provide a lightweight knowledge base for personal/work context.
Includes keyword search powered by SQLite FTS (notes_fts).

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]
from sqlalchemy import text  # type: ignore[import-untyped]

from models.database import get_session
from models.workflow import Note, normalize_tags
from utils.fts_query import sanitize_fts_query

logger = logging.getLogger(__name__)
router = APIRouter()


class NoteCreateRequest(BaseModel):
    """Create note payload."""

    title: str = Field(..., min_length=2, max_length=300)
    content: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    tags: Optional[List[str]] = None


@router.post("/", summary="Create Note")
async def create_note(request: NoteCreateRequest):
    """Create a note."""
    with get_session() as session:
        note = Note(
            id=str(uuid4()),
            project_id=request.project_id,
            title=request.title.strip(),
            content=request.content,
            tags=normalize_tags(request.tags),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(note)
        session.flush()
        return {"status": "success", "note": note.to_dict(include_content=True)}


@router.get("/search", summary="Search Notes")
async def search_notes(q: str = Query(...), limit: int = Query(10, ge=1, le=50)):
    """Keyword search notes via FTS.

    Declared before /{note_id} so FastAPI matches this literal path first.
    """
    match_query = sanitize_fts_query(q)
    if not match_query:
        return {"status": "success", "count": 0, "results": []}

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT note_id, bm25(notes_fts) as rank
                FROM notes_fts
                WHERE notes_fts MATCH :q
                ORDER BY rank ASC
                LIMIT :limit
                """),
            {"q": match_query, "limit": limit},
        ).fetchall()

        note_ids = [str(r[0]) for r in rows]
        if not note_ids:
            return {"status": "success", "count": 0, "results": []}

        notes: List[Note] = session.query(Note).filter(Note.id.in_(note_ids)).all()
        notes_by_id = {n.id: n for n in notes}

        results: List[Dict[str, Any]] = []
        for note_id, rank in rows:
            note = notes_by_id.get(str(note_id))
            if not note:
                continue
            score = 1.0 / (1.0 + float(rank or 0.0))
            item = note.to_dict(include_content=False)
            item["score"] = score
            results.append(item)

        return {"status": "success", "count": len(results), "results": results}


@router.get("/{note_id}", summary="Get Note")
async def get_note(note_id: str):
    """Get a note."""
    with get_session() as session:
        note = session.query(Note).filter(Note.id == note_id).first()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"status": "success", "note": note.to_dict(include_content=True)}
