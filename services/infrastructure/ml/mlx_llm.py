"""
MLX LLM client for local model inference via mlx_lm.server.

Provides chat completions using local MLX models (Qwen3, QwQ, Qwen2.5-Coder, Llama3.2).
Communicates with the OpenAI-compatible HTTP API exposed by mlx_lm.server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants & environment helpers
# ---------------------------------------------------------------------------

MLX_DEFAULT_HOST = "http://127.0.0.1:8080"
MLX_CHAT_ENDPOINT = "/v1/chat/completions"
MLX_MODELS_ENDPOINT = "/v1/models"
HTTP_TIMEOUT_SECONDS = 300
STREAM_DONE_SENTINEL = "[DONE]"


class MlxModel(str, Enum):
    """Available MLX models with their use cases."""

    QWEN3_32B = "mlx-community/Qwen3-32B-4bit"
    QWQ_32B = "mlx-community/QwQ-32B-4bit"
    QWEN_CODER_14B = "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"
    LLAMA_3B = "mlx-community/Llama-3.2-3B-Instruct-4bit"


# Model configurations with recommended settings
MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    MlxModel.QWEN3_32B: {
        "temperature": 0.7,
        "top_p": 0.9,
        "context_length": 32768,
        "description": "General-purpose 32B model for broad tasks",
        "use_cases": ["chat", "analysis", "summarization"],
    },
    MlxModel.QWQ_32B: {
        "temperature": 0.6,
        "top_p": 0.9,
        "context_length": 32768,
        "description": "Reasoning model for complex analysis and multi-step tasks",
        "use_cases": ["reasoning", "analysis", "planning", "complex_queries"],
    },
    MlxModel.QWEN_CODER_14B: {
        "temperature": 0.3,
        "top_p": 0.95,
        "context_length": 32768,
        "description": "Specialized for code generation, SQL queries, and technical tasks",
        "use_cases": ["code", "sql", "technical", "debugging"],
    },
    MlxModel.LLAMA_3B: {
        "temperature": 0.7,
        "top_p": 0.9,
        "context_length": 8192,
        "description": "Fast lightweight model for simple tasks and quick responses",
        "use_cases": ["simple", "fast", "summarization", "classification"],
    },
}


def _get_host() -> str:
    """Resolve MLX LM server host URL from environment."""
    return os.getenv("MLX_HOST", MLX_DEFAULT_HOST)


MLX_HOST: str = _get_host()
MLX_LLM_MODEL: str = os.getenv("MLX_LLM_MODEL", MlxModel.QWEN3_32B)
MLX_REASONING_MODEL: str = os.getenv("MLX_REASONING_MODEL", MlxModel.QWQ_32B)
MLX_FAST_MODEL: str = os.getenv("MLX_FAST_MODEL", MlxModel.LLAMA_3B)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ChatMessage:
    """Represents a chat message."""

    role: str  # "system", "user", "assistant"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ChatResponse:
    """Response from chat completion."""

    content: str
    model: str
    finish_reason: str
    total_duration_ms: float
    prompt_eval_count: int
    eval_count: int
    tool_calls: Optional[List[Dict[str, Any]]] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return bool(self.tool_calls)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass
class MlxLLMService:
    """
    Chat completions using local MLX LM server.

    Supports multiple models for different use cases:
    - Qwen3-32B for general tasks (main)
    - QwQ-32B for complex reasoning
    - Qwen2.5-Coder-14B for code/SQL generation
    - Llama-3.2-3B for fast simple responses

    Note: mlx_lm.server serves one model at a time. The model selection
    logic is kept for semantic routing but all requests go to the loaded model.
    """

    host: str
    default_model: str
    reasoning_model: str
    fast_model: str
    _client: httpx.Client = field(repr=False, default=None)

    def __post_init__(self) -> None:
        """Initialize HTTP client after dataclass init."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.host,
                timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
            )
            self._verify_server()

    def _verify_server(self) -> None:
        """Log server availability on startup."""
        try:
            response = self._client.get(MLX_MODELS_ENDPOINT)
            if response.status_code == 200:
                data = response.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                logger.info("MLX LM server available, models: %s", models)
            else:
                logger.warning(
                    "MLX LM server responded with status %d", response.status_code
                )
        except Exception as e:
            logger.warning("Could not reach MLX LM server at %s: %s", self.host, e)

    @classmethod
    def from_env(cls) -> "MlxLLMService":
        """Construct service from environment variables."""
        return cls(
            host=MLX_HOST,
            default_model=MLX_LLM_MODEL,
            reasoning_model=MLX_REASONING_MODEL,
            fast_model=MLX_FAST_MODEL,
        )

    def _select_model(
        self,
        model: Optional[str] = None,
        use_case: Optional[str] = None,
    ) -> str:
        """
        Select appropriate model based on use case or explicit choice.

        Args:
            model: Explicit model name (overrides use_case).
            use_case: Use case hint ("reasoning", "code", "fast", etc.).

        Returns:
            Model identifier string.
        """
        if model:
            return model

        if use_case:
            use_case_lower = use_case.lower()
            for model_id, config in MODEL_CONFIGS.items():
                if use_case_lower in config.get("use_cases", []):
                    return model_id

            if use_case_lower in ("reasoning", "analysis", "complex", "planning"):
                return self.reasoning_model
            elif use_case_lower in ("code", "sql", "technical", "debug"):
                return self.default_model
            elif use_case_lower in ("fast", "simple", "quick", "summary"):
                return self.fast_model

        return self.default_model

    def _get_model_config(self, model: str) -> Dict[str, Any]:
        """Get configuration for a model."""
        return MODEL_CONFIGS.get(
            model,
            {
                "temperature": 0.7,
                "top_p": 0.9,
                "context_length": 8192,
            },
        )

    def _build_messages(
        self,
        messages: List[ChatMessage | Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Convert messages to OpenAI chat format."""
        formatted: List[Dict[str, str]] = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if isinstance(msg, ChatMessage):
                formatted.append({"role": msg.role, "content": msg.content})
            else:
                formatted.append(msg)

        return formatted

    def chat(
        self,
        messages: List[ChatMessage | Dict[str, str]],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """
        Generate chat completion via MLX LM server.

        Args:
            messages: List of chat messages.
            model: Explicit model to use (optional).
            use_case: Use case for auto model selection ("reasoning", "code", "fast").
            temperature: Override default temperature.
            max_tokens: Maximum tokens to generate.
            tools: Tool definitions for function calling.
            system_prompt: System prompt to prepend.

        Returns:
            ChatResponse with generated content.
        """
        selected_model = self._select_model(model, use_case)
        config = self._get_model_config(selected_model)

        formatted_messages = self._build_messages(messages, system_prompt)

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": formatted_messages,
            "temperature": (
                temperature
                if temperature is not None
                else config.get("temperature", 0.7)
            ),
            "top_p": config.get("top_p", 0.9),
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        try:
            start_time = time.time()
            response = self._client.post(MLX_CHAT_ENDPOINT, json=payload)
            response.raise_for_status()
            duration_ms = (time.time() - start_time) * 1000

            data = response.json()
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            usage = data.get("usage", {})

            logger.info(
                "MLX chat completed: model=%s, tokens=%d, duration=%.0fms",
                selected_model,
                usage.get("completion_tokens", 0),
                duration_ms,
            )

            return ChatResponse(
                content=message.get("content", ""),
                model=selected_model,
                finish_reason=choice.get("finish_reason", "stop"),
                total_duration_ms=duration_ms,
                prompt_eval_count=usage.get("prompt_tokens", 0),
                eval_count=usage.get("completion_tokens", 0),
                tool_calls=message.get("tool_calls"),
            )

        except httpx.HTTPStatusError as e:
            logger.error("MLX server HTTP error %d: %s", e.response.status_code, e)
            raise
        except Exception as e:
            logger.error("MLX chat failed: %s", e, exc_info=True)
            raise

    def chat_stream(
        self,
        messages: List[ChatMessage | Dict[str, str]],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Iterator[str]:
        """
        Stream chat completion tokens.

        Args:
            messages: List of chat messages.
            model: Explicit model to use.
            use_case: Use case for model selection.
            temperature: Override temperature.
            max_tokens: Maximum tokens.
            system_prompt: System prompt.

        Yields:
            Content tokens as they are generated.
        """
        selected_model = self._select_model(model, use_case)
        config = self._get_model_config(selected_model)

        formatted_messages = self._build_messages(messages, system_prompt)

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": formatted_messages,
            "temperature": (
                temperature
                if temperature is not None
                else config.get("temperature", 0.7)
            ),
            "top_p": config.get("top_p", 0.9),
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            with self._client.stream(
                "POST", MLX_CHAT_ENDPOINT, json=payload
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: ") :]
                    if data_str.strip() == STREAM_DONE_SENTINEL:
                        break
                    chunk = json.loads(data_str)
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        yield delta

        except Exception as e:
            logger.error("MLX stream failed: %s", e, exc_info=True)
            raise

    async def chat_async(
        self,
        messages: List[ChatMessage | Dict[str, str]],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Async wrapper for chat completion."""
        return await asyncio.to_thread(
            self.chat,
            messages=messages,
            model=model,
            use_case=use_case,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            system_prompt=system_prompt,
        )

    async def chat_stream_async(
        self,
        messages: List[ChatMessage | Dict[str, str]],
        model: Optional[str] = None,
        use_case: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Async streaming chat completion.

        Uses httpx.AsyncClient for true async streaming.
        """
        selected_model = self._select_model(model, use_case)
        config = self._get_model_config(selected_model)

        formatted_messages = self._build_messages(messages, system_prompt)

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": formatted_messages,
            "temperature": (
                temperature
                if temperature is not None
                else config.get("temperature", 0.7)
            ),
            "top_p": config.get("top_p", 0.9),
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async_client = httpx.AsyncClient(
            base_url=self.host,
            timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
        )

        try:
            async with async_client.stream(
                "POST", MLX_CHAT_ENDPOINT, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: ") :]
                    if data_str.strip() == STREAM_DONE_SENTINEL:
                        break
                    chunk = json.loads(data_str)
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        yield delta

        except Exception as e:
            logger.error("MLX async stream failed: %s", e, exc_info=True)
            raise
        finally:
            await async_client.aclose()

    def generate_sql(
        self,
        prompt: str,
        schema_context: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate SQL query using the coder model.

        Args:
            prompt: Natural language query description.
            schema_context: Database schema context.
            max_tokens: Maximum tokens.

        Returns:
            Generated SQL query.
        """
        system = (
            "You are an expert SQL developer. Generate clean, efficient SQL queries.\n"
            "Only output the SQL query, no explanations. Use proper formatting and indentation."
        )

        if schema_context:
            system += f"\n\nDatabase Schema:\n{schema_context}"

        messages = [{"role": "user", "content": prompt}]
        response = self.chat(
            messages=messages,
            use_case="sql",
            system_prompt=system,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return response.content.strip()

    def analyze(
        self,
        data: str,
        question: str,
        max_tokens: int = 4096,
    ) -> str:
        """
        Perform deep analysis using the reasoning model.

        Args:
            data: Data or context to analyze.
            question: Analysis question.
            max_tokens: Maximum tokens.

        Returns:
            Analysis result.
        """
        system = (
            "You are an expert data analyst. Provide thorough, insightful analysis.\n"
            "Structure your response clearly with sections as needed."
        )

        prompt = f"Data/Context:\n{data}\n\nQuestion: {question}"
        messages = [{"role": "user", "content": prompt}]

        response = self.chat(
            messages=messages,
            use_case="reasoning",
            system_prompt=system,
            max_tokens=max_tokens,
        )
        return response.content

    def quick_response(
        self,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """
        Get fast response using lightweight model.

        Args:
            prompt: User prompt.
            max_tokens: Maximum tokens.

        Returns:
            Quick response.
        """
        messages = [{"role": "user", "content": prompt}]
        response = self.chat(
            messages=messages,
            use_case="fast",
            max_tokens=max_tokens,
        )
        return response.content

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models from MLX LM server."""
        try:
            response = self._client.get(MLX_MODELS_ENDPOINT)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    def health_check(self) -> Dict[str, Any]:
        """Check MLX LM server health and model availability."""
        result: Dict[str, Any] = {
            "status": "unknown",
            "host": self.host,
            "models": {
                "default": self.default_model,
                "reasoning": self.reasoning_model,
                "fast": self.fast_model,
            },
            "available_models": [],
        }

        try:
            models = self.list_models()
            available = [m.get("id", "") for m in models]
            result["available_models"] = available
            result["status"] = "healthy" if models else "no_models"

            for key in ["default", "reasoning", "fast"]:
                model_id = result["models"][key]
                result[f"{key}_available"] = any(model_id in m for m in available)

        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)

        return result


# ---------------------------------------------------------------------------
# Singleton instance (optionally wrapped with Langfuse tracing)
# ---------------------------------------------------------------------------

_raw_mlx_llm = MlxLLMService.from_env()


def _build_mlx_singleton() -> MlxLLMService:
    """Return traced or raw MLX service based on Langfuse configuration."""
    try:
        from services.infrastructure.observability.langfuse_client import (
            LANGFUSE_ENABLED,
        )

        if LANGFUSE_ENABLED:
            from services.infrastructure.observability.trace_mlx import (
                TracedMlxLLMService,
            )

            logger.info("MLX LLM singleton wrapped with Langfuse tracing")
            return TracedMlxLLMService(_raw_mlx_llm)  # type: ignore[return-value]
    except ImportError:
        pass

    return _raw_mlx_llm


mlx_llm = _build_mlx_singleton()
