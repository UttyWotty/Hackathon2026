"""
Model registry for managing LLM providers and model selection.

Central registry for all AI models (MLX local, Bedrock Claude) with routing
logic based on task type, cost, latency, and availability requirements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelProvider(str, Enum):
    """Available model providers."""

    MLX = "mlx"
    BEDROCK = "bedrock"


class TaskType(str, Enum):
    """Task types for intelligent model routing."""

    REASONING = "reasoning"  # Complex analysis, multi-step thinking
    CODE = "code"  # Code generation, SQL, technical
    FAST = "fast"  # Quick responses, simple tasks
    EMBEDDING = "embedding"  # Text embeddings for RAG
    CHAT = "chat"  # General conversation
    ANALYSIS = "analysis"  # Data analysis, insights
    SUMMARIZATION = "summarization"  # Text summarization


@dataclass(frozen=True)
class ModelSpec:
    """Specification for a model."""

    id: str
    provider: ModelProvider
    display_name: str
    description: str
    context_length: int
    supports_tools: bool
    supports_streaming: bool
    task_types: tuple[TaskType, ...]
    cost_tier: str  # "free", "low", "medium", "high"
    latency_tier: str  # "fast", "medium", "slow"
    parameters_b: float  # Size in billions


# Registry of all available models
MODEL_REGISTRY: Dict[str, ModelSpec] = {
    # MLX Local Models
    "mlx-community/Qwen3-32B-4bit": ModelSpec(
        id="mlx-community/Qwen3-32B-4bit",
        provider=ModelProvider.MLX,
        display_name="Qwen3 32B (4-bit)",
        description="General-purpose 32B model for broad tasks",
        context_length=32768,
        supports_tools=True,
        supports_streaming=True,
        task_types=(TaskType.CHAT, TaskType.ANALYSIS, TaskType.SUMMARIZATION),
        cost_tier="free",
        latency_tier="medium",
        parameters_b=32.0,
    ),
    "mlx-community/QwQ-32B-4bit": ModelSpec(
        id="mlx-community/QwQ-32B-4bit",
        provider=ModelProvider.MLX,
        display_name="QwQ 32B (4-bit)",
        description="Advanced reasoning model with chain-of-thought capabilities",
        context_length=32768,
        supports_tools=True,
        supports_streaming=True,
        task_types=(TaskType.REASONING, TaskType.ANALYSIS, TaskType.CHAT),
        cost_tier="free",
        latency_tier="slow",
        parameters_b=32.0,
    ),
    "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit": ModelSpec(
        id="mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
        provider=ModelProvider.MLX,
        display_name="Qwen 2.5 Coder 14B (4-bit)",
        description="Specialized for code generation, SQL, and technical tasks",
        context_length=32768,
        supports_tools=True,
        supports_streaming=True,
        task_types=(TaskType.CODE, TaskType.ANALYSIS, TaskType.CHAT),
        cost_tier="free",
        latency_tier="medium",
        parameters_b=14.0,
    ),
    "mlx-community/Llama-3.2-3B-Instruct-4bit": ModelSpec(
        id="mlx-community/Llama-3.2-3B-Instruct-4bit",
        provider=ModelProvider.MLX,
        display_name="Llama 3.2 3B (4-bit)",
        description="Fast lightweight model for simple tasks",
        context_length=8192,
        supports_tools=False,
        supports_streaming=True,
        task_types=(TaskType.FAST, TaskType.SUMMARIZATION, TaskType.CHAT),
        cost_tier="free",
        latency_tier="fast",
        parameters_b=3.0,
    ),
    "nomic-ai/nomic-embed-text-v1.5": ModelSpec(
        id="nomic-ai/nomic-embed-text-v1.5",
        provider=ModelProvider.MLX,
        display_name="Nomic Embed Text v1.5",
        description="High-quality text embeddings for semantic search",
        context_length=8192,
        supports_tools=False,
        supports_streaming=False,
        task_types=(TaskType.EMBEDDING,),
        cost_tier="free",
        latency_tier="fast",
        parameters_b=0.137,
    ),
    # Bedrock Models (for reference/fallback)
    "anthropic.claude-3-5-sonnet-20241022-v2:0": ModelSpec(
        id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        provider=ModelProvider.BEDROCK,
        display_name="Claude 3.5 Sonnet",
        description="Balanced performance Claude model via AWS Bedrock",
        context_length=200000,
        supports_tools=True,
        supports_streaming=True,
        task_types=(
            TaskType.REASONING,
            TaskType.CODE,
            TaskType.ANALYSIS,
            TaskType.CHAT,
        ),
        cost_tier="medium",
        latency_tier="medium",
        parameters_b=0.0,  # Unknown
    ),
}


# Task-to-model routing preferences (MLX-first)
TASK_ROUTING: Dict[TaskType, List[str]] = {
    TaskType.REASONING: [
        "mlx-community/QwQ-32B-4bit",
        "mlx-community/Qwen3-32B-4bit",
    ],
    TaskType.CODE: [
        "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
        "mlx-community/Qwen3-32B-4bit",
    ],
    TaskType.FAST: [
        "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "mlx-community/Qwen3-32B-4bit",
    ],
    TaskType.EMBEDDING: [
        "nomic-ai/nomic-embed-text-v1.5",
    ],
    TaskType.CHAT: [
        "mlx-community/Qwen3-32B-4bit",
        "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "mlx-community/QwQ-32B-4bit",
    ],
    TaskType.ANALYSIS: [
        "mlx-community/QwQ-32B-4bit",
        "mlx-community/Qwen3-32B-4bit",
    ],
    TaskType.SUMMARIZATION: [
        "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "mlx-community/Qwen3-32B-4bit",
    ],
}


class ModelRegistry:
    """
    Central registry for model discovery and selection.

    Provides intelligent routing based on task requirements.
    """

    def __init__(self) -> None:
        """Initialize registry with default models."""
        self._models = MODEL_REGISTRY.copy()
        self._routing = TASK_ROUTING.copy()

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Get model specification by ID."""
        return self._models.get(model_id)

    def list_models(
        self,
        provider: Optional[ModelProvider] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[ModelSpec]:
        """
        List models with optional filtering.

        Args:
            provider: Filter by provider.
            task_type: Filter by supported task type.

        Returns:
            List of matching model specs.
        """
        models = list(self._models.values())

        if provider:
            models = [m for m in models if m.provider == provider]

        if task_type:
            models = [m for m in models if task_type in m.task_types]

        return models

    def select_model(
        self,
        task_type: TaskType,
        prefer_fast: bool = False,
        require_tools: bool = False,
        require_streaming: bool = False,
        min_context: int = 0,
    ) -> Optional[ModelSpec]:
        """
        Select best model for a task.

        Args:
            task_type: Type of task to perform.
            prefer_fast: Prefer lower latency over capability.
            require_tools: Model must support tool calling.
            require_streaming: Model must support streaming.
            min_context: Minimum context length required.

        Returns:
            Best matching model spec or None.
        """
        candidates = self._routing.get(task_type, [])

        for model_id in candidates:
            model = self._models.get(model_id)
            if not model:
                continue

            if require_tools and not model.supports_tools:
                continue
            if require_streaming and not model.supports_streaming:
                continue
            if model.context_length < min_context:
                continue

            return model

        # Fallback: try any model that matches requirements
        for model in self._models.values():
            if task_type not in model.task_types:
                continue
            if require_tools and not model.supports_tools:
                continue
            if require_streaming and not model.supports_streaming:
                continue
            if model.context_length < min_context:
                continue
            return model

        return None

    def get_recommended_model(self, query: str) -> str:
        """
        Get recommended model based on query content analysis.

        Simple heuristic-based routing:
        - SQL/code keywords -> Qwen Coder
        - Analysis/why/explain -> QwQ reasoning
        - Short/simple -> Llama fast

        Args:
            query: User query text.

        Returns:
            Recommended model ID.
        """
        query_lower = query.lower()

        # Code/SQL indicators
        code_keywords = [
            "sql",
            "query",
            "code",
            "function",
            "class",
            "debug",
            "error",
            "fix",
        ]
        if any(kw in query_lower for kw in code_keywords):
            return "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"

        # Reasoning indicators
        reasoning_keywords = [
            "analyze",
            "explain",
            "why",
            "compare",
            "evaluate",
            "plan",
            "strategy",
        ]
        if any(kw in query_lower for kw in reasoning_keywords):
            return "mlx-community/QwQ-32B-4bit"

        # Short queries -> fast model
        SHORT_QUERY_THRESHOLD = 100
        if len(query) < SHORT_QUERY_THRESHOLD:
            return "mlx-community/Llama-3.2-3B-Instruct-4bit"

        # Default to main model
        return "mlx-community/Qwen3-32B-4bit"

    def to_dict(self) -> Dict[str, Any]:
        """Export registry as dictionary for API responses."""
        return {
            "models": {
                model_id: {
                    "id": spec.id,
                    "provider": spec.provider.value,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "context_length": spec.context_length,
                    "supports_tools": spec.supports_tools,
                    "supports_streaming": spec.supports_streaming,
                    "task_types": [t.value for t in spec.task_types],
                    "cost_tier": spec.cost_tier,
                    "latency_tier": spec.latency_tier,
                }
                for model_id, spec in self._models.items()
            },
            "routing": {task.value: models for task, models in self._routing.items()},
        }


# Singleton instance
model_registry = ModelRegistry()
