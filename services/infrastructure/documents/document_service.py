"""
Document service for upload, extraction, indexing, and search.

Design goals:
  - Minimal dependencies (pure Python + SQLite + SQLAlchemy).
  - Provide both keyword search (SQLite FTS) and a lightweight semantic-ish search
    via simple hashed bag-of-words vectors.

TODO:
  - Add robust parsers for PDF/DOCX (extract text).
  - Replace hash-vector with real embeddings and a vector store.

Author: Utku Gulbardak
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import aiofiles  # type: ignore[import-untyped]
from sqlalchemy import text  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]

from models.documents import Document
from services.infrastructure.ml.embeddings import embedding_service
from utils.fts_query import sanitize_fts_query
from utils.redaction import redact_text

logger = logging.getLogger(__name__)


_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class DocumentSearchResult:
    """Search hit representation."""

    doc: Document
    score: float
    snippet: str


def _sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _tokenize(text_value: str) -> List[str]:
    """Tokenize text for simple hashed embedding."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text_value or "")]


def compute_hash_embedding(text_value: str, *, dims: int = 256) -> List[float]:
    """
    Compute a lightweight hashed bag-of-words embedding.

    Args:
        text_value: Input text.
        dims: Embedding dimension.

    Returns:
        List[float] length dims (L2-normalized).
    """
    vec = [0.0] * dims
    tokens = _tokenize(text_value)
    if not tokens:
        return vec

    for tok in tokens:
        h = int(
            hashlib.md5(tok.encode("utf-8")).hexdigest(), 16
        )  # noqa: S324 (non-crypto use)
        idx = h % dims
        vec[idx] += 1.0

    # L2 normalize
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def try_extract_text(filename: str, content_type: Optional[str], data: bytes) -> str:
    """
    Best-effort text extraction.

    Currently supports:
      - text/* content types
      - .txt / .md / .json / .csv extensions (UTF-8 decode)

    TODO: Add PDF/DOCX extraction when desired.
    """
    name = (filename or "").lower()
    if content_type and content_type.startswith("text/"):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    if any(name.endswith(ext) for ext in [".txt", ".md", ".json", ".csv", ".log"]):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    return ""


async def save_document_file(storage_dir: Path, filename: str, data: bytes) -> Path:
    """
    Persist uploaded file to disk.

    Args:
        storage_dir: Destination directory.
        filename: Original filename.
        data: File bytes.

    Returns:
        Saved file path.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_name = filename.replace("/", "_").replace("\\", "_")
    doc_id = str(uuid4())
    path = storage_dir / f"{doc_id}_{safe_name}"
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
    return path


async def ingest_document(
    *,
    session: Session,
    filename: str,
    content_type: Optional[str],
    data: bytes,
    metadata: Optional[Dict[str, Any]] = None,
    storage_dir: Path = Path("storage/documents"),
) -> Document:
    """
    Ingest a document: save to disk, extract text, compute embedding, persist DB row.

    Args:
        session: SQLAlchemy session.
        filename: Original file name.
        content_type: MIME type.
        data: File bytes.
        metadata: Optional metadata JSON.
        storage_dir: Storage directory.

    Returns:
        Created Document row.
    """
    saved_path = await save_document_file(storage_dir, filename, data)
    extracted = try_extract_text(filename, content_type, data)

    # Always redact extracted text before persisting in case the user uploaded secrets.
    extracted = redact_text(extracted)

    # Prefer real Bedrock embeddings when enabled; fallback to lightweight hash-vector.
    embedding: Optional[List[float]] = None
    if extracted:
        embedding = await embedding_service.get_embedding_async(extracted)
        if not embedding:
            # Fallback (kept for local/dev without AWS credentials).
            embedding = compute_hash_embedding(extracted)

    doc = Document(
        id=saved_path.name.split("_", 1)[0],
        filename=filename,
        content_type=content_type,
        storage_path=str(saved_path),
        size_bytes=len(data),
        sha256=_sha256_bytes(data),
        extracted_text=extracted if extracted else None,
        metadata_json=metadata or {},
        embedding=embedding,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(doc)
    session.flush()
    return doc


def update_document_metadata(
    session: Session, *, doc_id: str, metadata: Dict[str, Any]
) -> Optional[Document]:
    """Update metadata for an existing document."""
    doc = session.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None
    doc.metadata_json = metadata
    doc.updated_at = datetime.utcnow()
    session.add(doc)
    return doc


def keyword_search(
    session: Session, *, query: str, limit: int = 10
) -> List[Tuple[str, float]]:
    """
    Keyword search via SQLite FTS.

    Returns doc_id list in best-first order.
    """
    # FTS5 bm25: lower is better. We invert it into a "score" where higher is better.
    # NOTE: query is passed as param (no SQL injection) and sanitized so FTS5
    # operator characters (e.g. "-" in "run-rate") cannot raise MATCH errors.
    match_query = sanitize_fts_query(query)
    if not match_query:
        return []
    rows = session.execute(
        text("""
            SELECT doc_id, bm25(documents_fts) as rank
            FROM documents_fts
            WHERE documents_fts MATCH :q
            ORDER BY rank ASC
            LIMIT :limit
            """),
        {"q": match_query, "limit": limit},
    ).fetchall()
    results: List[Tuple[str, float]] = []
    for doc_id, rank in rows:
        score = 1.0 / (1.0 + float(rank or 0.0))
        results.append((str(doc_id), score))
    return results


async def semantic_search(
    session: Session,
    *,
    query: str,
    limit: int = 10,
    candidate_pool: int = 200,
) -> List[Tuple[str, float]]:
    """
    Lightweight semantic search using stored hash-vectors.

    Strategy:
      - If FTS returns candidates, compute similarity among those.
      - Else compute similarity across all docs with embeddings (up to candidate_pool).
    """
    # Prefer real query embedding; fallback to hash-vector if disabled/unavailable.
    qvec = await embedding_service.get_embedding_async(query)
    if not qvec:
        qvec = compute_hash_embedding(query)

    candidates = keyword_search(session, query=query, limit=min(candidate_pool, 50))
    doc_ids = [doc_id for doc_id, _ in candidates]

    docs_query = session.query(Document).filter(Document.embedding.isnot(None))
    if doc_ids:
        docs = docs_query.filter(Document.id.in_(doc_ids)).all()
    else:
        docs = docs_query.limit(candidate_pool).all()

    scored: List[Tuple[str, float]] = []
    for doc in docs:
        emb = doc.embedding or []
        if not isinstance(emb, list):
            continue
        # Titan vectors are often normalized (if configured). If both vectors are normalized,
        # cosine similarity equals dot product. We keep cosine_similarity for safety.
        scored.append((doc.id, cosine_similarity(qvec, emb)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
