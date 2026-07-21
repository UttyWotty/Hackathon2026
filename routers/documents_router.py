"""
Documents Router.

Provides structured document ingestion and retrieval endpoints intended for:
  - analytics inputs
  - LLM workflows (RAG / semantic search)

Endpoints:
  - POST /documents/upload
  - GET  /documents/search
  - POST /documents/metadata

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import (  # type: ignore[import-untyped]
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from models.database import get_session
from models.documents import Document, safe_text_preview
from services.infrastructure.documents.document_service import (
    ingest_document,
    keyword_search,
    semantic_search,
    update_document_metadata,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""

    status: str
    document: Dict[str, Any]


class DocumentMetadataRequest(BaseModel):
    """Update document metadata payload."""

    document_id: str = Field(..., description="Document id returned at upload time")
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("/", summary="Documents Service Info")
async def documents_info():
    """Info endpoint for documents service."""
    return {
        "service": "Documents Service",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "upload": "POST /documents/upload",
            "search": "GET /documents/search",
            "metadata": "POST /documents/metadata",
        },
        "notes": [
            "Keyword search uses SQLite FTS (documents_fts).",
            "Semantic search uses a lightweight hash-vector embedding (replaceable).",
        ],
    }


@router.post(
    "/upload", summary="Upload Document", response_model=DocumentUploadResponse
)
async def upload_document(
    file: UploadFile = File(...),
):
    """
    Upload a document.

    Notes:
      - Stores the raw file under `storage/documents/`.
      - Attempts best-effort text extraction for text-like files.
      - Computes a lightweight embedding for semantic-ish search.
    """
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload")

        with get_session() as session:
            doc = await ingest_document(
                session=session,
                filename=file.filename or "uploaded_file",
                content_type=file.content_type,
                data=data,
                metadata={"source": "upload"},
            )

            # Ensure the row is loaded for response.
            session.refresh(doc)
            payload = doc.to_dict(include_text=False)
            payload["text_preview"] = safe_text_preview(doc.extracted_text)

        return {"status": "success", "document": payload}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Document upload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Document upload failed")


@router.get("/search", summary="Search Documents")
async def search_documents(
    q: str = Query(..., description="Search query"),
    mode: str = Query(
        "keyword",
        description="Search mode: keyword or semantic",
        pattern="^(keyword|semantic)$",
    ),
    limit: int = Query(10, ge=1, le=50),
    include_text: bool = Query(False, description="Include extracted text in results"),
):
    """
    Search documents by keyword (FTS) or semantic-ish similarity.

    Returns a list of documents with a `score` and `text_preview`.
    """
    with get_session() as session:
        if mode == "semantic":
            hits = await semantic_search(session, query=q, limit=limit)
        else:
            hits = keyword_search(session, query=q, limit=limit)

        doc_ids = [doc_id for doc_id, _ in hits]
        if not doc_ids:
            return {"status": "success", "count": 0, "results": []}

        docs: List[Document] = (
            session.query(Document).filter(Document.id.in_(doc_ids)).all()
        )
        docs_by_id = {d.id: d for d in docs}

        results: List[Dict[str, Any]] = []
        for doc_id, score in hits:
            doc = docs_by_id.get(doc_id)
            if not doc:
                continue
            item = doc.to_dict(include_text=include_text)
            item["score"] = score
            item["text_preview"] = safe_text_preview(doc.extracted_text)
            results.append(item)

        return {"status": "success", "count": len(results), "results": results}


@router.post("/metadata", summary="Update Document Metadata")
async def set_document_metadata(request: DocumentMetadataRequest):
    """
    Update metadata for a document.

    Metadata is stored as JSON and can be used for filtering and LLM context.
    """
    with get_session() as session:
        doc = update_document_metadata(
            session, doc_id=request.document_id, metadata=request.metadata
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        session.flush()
        return {"status": "success", "document": doc.to_dict(include_text=False)}
