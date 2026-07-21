"""
Document ingestion and indexing models.

This module stores uploaded documents and extracted text used for:
  - keyword search (SQLite FTS)
  - lightweight semantic-ish search (vector stored per document)

TODO: Replace the lightweight embedding with a proper embedding model (e.g.,
      OpenAI/Bedrock embeddings or sentence-transformers) when desired.

Author: Utku Gulbardak
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from .database import Base


class Document(Base):
    """Uploaded document with extracted text and optional embedding."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)  # UUID

    filename = Column(String(500), nullable=False, index=True)
    content_type = Column(String(200), nullable=True)
    storage_path = Column(String(1000), nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=True, index=True)

    extracted_text = Column(Text, nullable=True)
    metadata_json = Column(
        "metadata", JSON, nullable=True
    )  # "metadata" reserved workaround
    embedding = Column(JSON, nullable=True)  # list[float] stored as JSON

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, *, include_text: bool = False) -> Dict[str, Any]:
        """Convert model to dict for API responses."""
        payload: Dict[str, Any] = {
            "id": self.id,
            "filename": self.filename,
            "content_type": self.content_type,
            "storage_path": self.storage_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "metadata": self.metadata_json or {},
            "has_text": bool(self.extracted_text),
            "has_embedding": bool(self.embedding),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_text:
            payload["extracted_text"] = self.extracted_text
        return payload


def safe_text_preview(text: Optional[str], limit: int = 500) -> str:
    """
    Create a safe preview of extracted text.

    Args:
        text: Source text.
        limit: Max chars.

    Returns:
        Preview string.
    """
    if not text:
        return ""
    clean = " ".join(text.split())
    return clean[:limit]
