"""
Config Router.

Allows managing prompts and feature flags without code changes.

Endpoints:
  - GET  /config/prompts
  - POST /config/prompts
  - GET  /config/feature-flags
  - POST /config/feature-flags

TODO:
  - Add auth/role gating for write operations.

Author: Utku Gulbardak
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from models.config import FeatureFlag, PromptConfig
from models.database import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


class PromptUpsertRequest(BaseModel):
    """Upsert prompt payload."""

    key: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpsertRequest(BaseModel):
    """Upsert feature flag payload."""

    key: str = Field(..., min_length=1, max_length=200)
    enabled: bool = False
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.get("/prompts", summary="List Prompts")
async def list_prompts():
    """List all prompt configs."""
    with get_session() as session:
        prompts = session.query(PromptConfig).all()
        return {
            "status": "success",
            "count": len(prompts),
            "prompts": [p.to_dict() for p in prompts],
        }


@router.post("/prompts", summary="Upsert Prompt")
async def upsert_prompt(request: PromptUpsertRequest):
    """Create or update a prompt."""
    with get_session() as session:
        prompt = (
            session.query(PromptConfig).filter(PromptConfig.key == request.key).first()
        )
        if not prompt:
            prompt = PromptConfig(
                key=request.key,
                content=request.content,
                metadata_json=request.metadata,
                updated_at=datetime.utcnow(),
            )
        else:
            prompt.content = request.content
            prompt.metadata_json = request.metadata
            prompt.updated_at = datetime.utcnow()
        session.add(prompt)
        return {"status": "success", "prompt": prompt.to_dict()}


@router.get("/feature-flags", summary="List Feature Flags")
async def list_feature_flags():
    """List all feature flags."""
    with get_session() as session:
        flags = session.query(FeatureFlag).all()
        return {
            "status": "success",
            "count": len(flags),
            "feature_flags": [f.to_dict() for f in flags],
        }


@router.post("/feature-flags", summary="Upsert Feature Flag")
async def upsert_feature_flag(request: FeatureFlagUpsertRequest):
    """Create or update a feature flag."""
    with get_session() as session:
        flag = session.query(FeatureFlag).filter(FeatureFlag.key == request.key).first()
        if not flag:
            flag = FeatureFlag(
                key=request.key,
                enabled=request.enabled,
                payload=request.payload,
                updated_at=datetime.utcnow(),
            )
        else:
            flag.enabled = request.enabled
            flag.payload = request.payload
            flag.updated_at = datetime.utcnow()
        session.add(flag)
        return {"status": "success", "feature_flag": flag.to_dict()}
