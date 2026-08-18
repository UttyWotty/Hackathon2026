"""
Observability package for LLM call tracing and automated scoring.

Provides Langfuse integration via transparent proxy wrappers around MLX and Bedrock
LLM clients, plus automated scoring pipelines for latency, cost, and quality.
"""

from services.infrastructure.observability.langfuse_client import (
    get_langfuse,
    shutdown_langfuse,
)

__all__ = [
    "get_langfuse",
    "shutdown_langfuse",
]
