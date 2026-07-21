"""
ML/AI infrastructure for Manufacturing API.

Provides local LLM inference (MLX), embeddings, and ML utilities.
Supports multiple models: Qwen3, QwQ, Qwen2.5-Coder, Llama 3.2, Nomic Embed.
"""

from .embeddings import EmbeddingService, embedding_service
from .mlx_llm import ChatMessage, ChatResponse, MlxLLMService, mlx_llm
from .model_registry import (
    ModelProvider,
    ModelRegistry,
    ModelSpec,
    TaskType,
    model_registry,
)

__all__ = [
    # Embeddings
    "EmbeddingService",
    "embedding_service",
    # LLM
    "MlxLLMService",
    "mlx_llm",
    "ChatMessage",
    "ChatResponse",
    # Registry
    "ModelRegistry",
    "model_registry",
    "ModelProvider",
    "ModelSpec",
    "TaskType",
]
