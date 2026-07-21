"""
Config models for prompts and feature flags.

These are used to adjust LLM behavior and server toggles without code changes.

Author: Utku Gulbardak
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    String,
    Text,
)

from .database import Base


class PromptConfig(Base):
    """Named prompt templates and guardrails."""

    __tablename__ = "config_prompts"

    key = Column(String(200), primary_key=True)
    content = Column(Text, nullable=False)
    metadata_json = Column("metadata", JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "content": self.content,
            "metadata": self.metadata_json or {},
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class FeatureFlag(Base):
    """Global feature flags."""

    __tablename__ = "feature_flags"

    key = Column(String(200), primary_key=True)
    enabled = Column(Boolean, default=False, nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "payload": self.payload or {},
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
