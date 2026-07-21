"""
MLX LLM API router for local model inference.

Provides REST endpoints for chat completions, model selection, and health checks
using local MLX models (Qwen3, QwQ, Qwen2.5-Coder, Llama3.2).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.status import (
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from services.infrastructure.ml.mlx_llm import mlx_llm
from services.infrastructure.ml.model_registry import (
    ModelProvider,
    TaskType,
    model_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mlx")

# Returned when the local MLX inference server cannot be reached, so clients see
# a 503 (dependency down) rather than a 500 that reads as an application crash.
LLM_UNAVAILABLE_DETAIL = (
    "LLM backend unavailable: the local MLX inference server is not reachable."
)


def _llm_http_error(exc: Exception) -> HTTPException:
    """Map an LLM call failure to 503 when it is a connectivity error, else 500."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError)):
        return HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE, detail=LLM_UNAVAILABLE_DETAIL
        )
    return HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class ChatMessageRequest(BaseModel):
    """Chat message in request."""

    role: str = Field(..., description="Message role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat completion request."""

    messages: List[ChatMessageRequest] = Field(..., description="Chat messages")
    model: Optional[str] = Field(None, description="Specific model to use")
    use_case: Optional[str] = Field(
        None,
        description="Use case for auto model selection: reasoning, code, fast, analysis",
    )
    temperature: Optional[float] = Field(
        None, ge=0, le=2, description="Sampling temperature"
    )
    max_tokens: Optional[int] = Field(
        None, gt=0, le=32768, description="Max tokens to generate"
    )
    system_prompt: Optional[str] = Field(None, description="System prompt to prepend")
    stream: bool = Field(False, description="Enable streaming response")


class ChatResponse(BaseModel):
    """Chat completion response."""

    content: str
    model: str
    finish_reason: str
    usage: Dict[str, int]
    duration_ms: float


class GenerateSQLRequest(BaseModel):
    """SQL generation request."""

    prompt: str = Field(..., description="Natural language description of the query")
    schema_context: Optional[str] = Field(None, description="Database schema context")
    max_tokens: int = Field(2048, description="Max tokens")


class AnalyzeRequest(BaseModel):
    """Analysis request."""

    data: str = Field(..., description="Data or context to analyze")
    question: str = Field(..., description="Analysis question")
    max_tokens: int = Field(4096, description="Max tokens")


class QuickRequest(BaseModel):
    """Quick response request."""

    prompt: str = Field(..., description="User prompt")
    max_tokens: int = Field(512, description="Max tokens")


class ModelSelectRequest(BaseModel):
    """Model selection request."""

    query: str = Field(..., description="Query to analyze for model recommendation")
    task_type: Optional[str] = Field(None, description="Explicit task type")
    require_tools: bool = Field(False, description="Require tool support")
    require_streaming: bool = Field(False, description="Require streaming support")
    min_context: int = Field(0, description="Minimum context length")


# ---------------------------------------------------------------------------
# Core LLM Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat_completion(request: ChatRequest) -> ChatResponse:
    """
    Generate chat completion using local MLX models.

    Automatically selects model based on use_case or uses specified model.

    Use cases:
    - reasoning: Complex analysis (QwQ-32B)
    - code: Code/SQL generation (Qwen2.5-Coder-14B)
    - fast: Quick responses (Llama-3.2-3B)
    """
    try:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        response = await mlx_llm.chat_async(
            messages=messages,
            model=request.model,
            use_case=request.use_case,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            system_prompt=request.system_prompt,
        )

        return ChatResponse(
            content=response.content,
            model=response.model,
            finish_reason=response.finish_reason,
            usage={
                "prompt_tokens": response.prompt_eval_count,
                "completion_tokens": response.eval_count,
                "total_tokens": response.prompt_eval_count + response.eval_count,
            },
            duration_ms=response.total_duration_ms,
        )

    except Exception as e:
        logger.error("Chat completion failed: %s", e, exc_info=True)
        raise _llm_http_error(e)


@router.post("/chat/stream")
async def chat_completion_stream(request: ChatRequest) -> StreamingResponse:
    """
    Stream chat completion tokens.

    Returns Server-Sent Events with content tokens.
    """

    async def generate():
        try:
            messages = [
                {"role": m.role, "content": m.content} for m in request.messages
            ]

            async for token in mlx_llm.chat_stream_async(
                messages=messages,
                model=request.model,
                use_case=request.use_case,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                system_prompt=request.system_prompt,
            ):
                yield f"data: {token}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Stream failed: %s", e)
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/generate/sql")
async def generate_sql(request: GenerateSQLRequest) -> Dict[str, str]:
    """
    Generate SQL query using the coder model.

    Optimized for Snowflake SQL syntax.
    """
    try:
        sql = mlx_llm.generate_sql(
            prompt=request.prompt,
            schema_context=request.schema_context,
            max_tokens=request.max_tokens,
        )
        return {"sql": sql, "model": mlx_llm.default_model}

    except Exception as e:
        logger.error("SQL generation failed: %s", e)
        raise _llm_http_error(e)


@router.post("/analyze")
async def analyze_data(request: AnalyzeRequest) -> Dict[str, str]:
    """
    Perform deep analysis using the reasoning model.

    Best for complex multi-step analysis requiring chain-of-thought.
    """
    try:
        analysis = mlx_llm.analyze(
            data=request.data,
            question=request.question,
            max_tokens=request.max_tokens,
        )
        return {"analysis": analysis, "model": mlx_llm.reasoning_model}

    except Exception as e:
        logger.error("Analysis failed: %s", e)
        raise _llm_http_error(e)


@router.post("/quick")
async def quick_response(request: QuickRequest) -> Dict[str, str]:
    """
    Get fast response using lightweight model.

    Best for simple questions and quick tasks.
    """
    try:
        response = mlx_llm.quick_response(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
        )
        return {"response": response, "model": mlx_llm.fast_model}

    except Exception as e:
        logger.error("Quick response failed: %s", e)
        raise _llm_http_error(e)


@router.post("/select-model")
async def select_model(request: ModelSelectRequest) -> Dict[str, Any]:
    """
    Get recommended model for a query or task.

    Uses heuristics to determine best model based on query content
    and task requirements.
    """
    if request.task_type:
        try:
            task = TaskType(request.task_type)
            model = model_registry.select_model(
                task_type=task,
                require_tools=request.require_tools,
                require_streaming=request.require_streaming,
                min_context=request.min_context,
            )
            if model:
                return {
                    "recommended_model": model.id,
                    "display_name": model.display_name,
                    "reason": f"Best model for {task.value} tasks",
                    "spec": {
                        "context_length": model.context_length,
                        "supports_tools": model.supports_tools,
                        "latency_tier": model.latency_tier,
                    },
                }
        except ValueError:
            pass

    recommended = model_registry.get_recommended_model(request.query)
    model = model_registry.get_model(recommended)

    return {
        "recommended_model": recommended,
        "display_name": model.display_name if model else recommended,
        "reason": "Based on query content analysis",
        "spec": {
            "context_length": model.context_length if model else None,
            "supports_tools": model.supports_tools if model else None,
            "latency_tier": model.latency_tier if model else None,
        },
    }


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """
    List all available MLX models.

    Returns both configured models and actually available models.
    """
    try:
        available = mlx_llm.list_models()
        available_names = [m.get("id", "") for m in available]

        registry_models = model_registry.list_models(provider=ModelProvider.MLX)

        return {
            "available_models": available_names,
            "configured_models": [
                {
                    "id": m.id,
                    "display_name": m.display_name,
                    "description": m.description,
                    "task_types": [t.value for t in m.task_types],
                    "latency_tier": m.latency_tier,
                    "is_available": any(m.id in name for name in available_names),
                }
                for m in registry_models
            ],
            "defaults": {
                "default": mlx_llm.default_model,
                "reasoning": mlx_llm.reasoning_model,
                "fast": mlx_llm.fast_model,
            },
        }

    except Exception as e:
        logger.error("List models failed: %s", e)
        raise _llm_http_error(e)


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Check MLX LM server health and model availability.

    Returns status of each configured model.
    """
    try:
        health = mlx_llm.health_check()
        return health

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@router.get("/registry")
async def get_registry() -> Dict[str, Any]:
    """
    Get full model registry with routing configuration.

    Useful for understanding model capabilities and routing logic.
    """
    return model_registry.to_dict()


# =============================================================================
# Manufacturing Chat Assistant Endpoints
# =============================================================================

from services.infrastructure.ml.chat_assistant import chat_assistant  # noqa: E402


class ManufacturingChatRequest(BaseModel):
    """Manufacturing chat request."""

    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field("default", description="Conversation session ID")
    equipment_code: Optional[str] = Field(None, description="Equipment filter")
    data_context: Optional[Dict[str, Any]] = Field(
        None, description="Data context for analysis"
    )


class ManufacturingChatResponse(BaseModel):
    """Manufacturing chat response."""

    content: str = Field(..., description="Assistant response")
    intent: str = Field(..., description="Detected user intent")
    session_id: str = Field(..., description="Session ID")
    type: Optional[str] = Field(None, description="Response type")
    sql: Optional[str] = Field(None, description="Generated SQL if applicable")
    model: Optional[str] = Field(None, description="Model used")
    output_files: Optional[Dict[str, str]] = Field(
        None, description="Generated file paths"
    )


class ReportSummaryRequest(BaseModel):
    """Report summary request."""

    report_type: str = Field(..., description="Report type: runrate or risk_tower")
    report_data: Dict[str, Any] = Field(..., description="Report data to summarize")


class AnomalyExplainRequest(BaseModel):
    """Anomaly explanation request."""

    anomaly_data: Dict[str, Any] = Field(..., description="Anomaly detection results")
    historical_context: Optional[str] = Field(None, description="Historical patterns")


@router.post("/assistant/chat", response_model=ManufacturingChatResponse)
async def manufacturing_chat(
    request: ManufacturingChatRequest,
) -> ManufacturingChatResponse:
    """
    Chat with the Manufacturing Analytics Assistant.

    This is your intelligent assistant for:
    - Querying production data
    - Analyzing metrics (MTTR, MTBF, efficiency)
    - Generating SQL queries
    - Explaining reports (RunRate, Risk Tower)
    - Troubleshooting production issues

    The assistant automatically detects your intent and uses the appropriate
    model and approach to help you.

    Example:
        ```json
        {
            "message": "Why is equipment EMA-4104 showing high MTTR?",
            "session_id": "user123",
            "equipment_code": "EMA-4104"
        }
        ```
    """
    try:
        response = await chat_assistant.chat(
            message=request.message,
            session_id=request.session_id or "default",
            data_context=request.data_context,
            equipment_code=request.equipment_code,
        )

        return ManufacturingChatResponse(
            content=response.get("content", ""),
            intent=response.get("intent", "general_chat"),
            session_id=response.get("session_id", request.session_id),
            type=response.get("type"),
            sql=response.get("sql"),
            model=response.get("model"),
            output_files=response.get("output_files"),
        )

    except Exception as e:
        logger.error("Manufacturing chat failed: %s", e, exc_info=True)
        raise _llm_http_error(e)


@router.post("/assistant/chat/stream")
async def manufacturing_chat_stream(
    request: ManufacturingChatRequest,
) -> StreamingResponse:
    """
    Stream chat response from Manufacturing Assistant.

    Returns Server-Sent Events for real-time response display.
    """

    async def generate():
        try:
            context = chat_assistant.get_or_create_conversation(
                request.session_id or "default"
            )

            from services.infrastructure.ml.chat_assistant import SYSTEM_PROMPT

            messages = context.get_chat_messages()
            messages.append({"role": "user", "content": request.message})

            async for token in mlx_llm.chat_stream_async(
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                use_case="fast",
            ):
                yield f"data: {token}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Stream chat failed: %s", e)
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/assistant/summarize")
async def summarize_report(request: ReportSummaryRequest) -> Dict[str, Any]:
    """
    Generate executive summary of any analysis report.

    Supported report types:
    - roi: Return on Investment analysis
    - runrate: Production Run Rate analysis
    - risk_tower: Risk Tower equipment rankings
    - rca: Root Cause Analysis
    - ct_efficiency: Cycle Time Efficiency
    - ct_deviation: Cycle Time Deviation
    - tooling_eol: Tooling End-of-Life prediction
    - capacity: Capacity/OEE analysis

    Returns AI-generated narrative summary with key findings
    and recommendations.
    """
    try:
        result = chat_assistant.summarize_any_report(
            report_type=request.report_type,
            report_data=request.report_data,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Report summarization failed: %s", e, exc_info=True)
        raise _llm_http_error(e)


@router.post("/assistant/explain-anomaly")
async def explain_anomaly(request: AnomalyExplainRequest) -> Dict[str, Any]:
    """
    Get AI explanation for a detected anomaly.

    Provides probable causes, impact assessment, and recommended actions.
    """
    try:
        result = chat_assistant.explain_anomaly(
            anomaly_data=request.anomaly_data,
            historical_context=request.historical_context,
        )
        return result

    except Exception as e:
        logger.error("Anomaly explanation failed: %s", e, exc_info=True)
        raise _llm_http_error(e)


@router.delete("/assistant/session/{session_id}")
async def clear_assistant_session(session_id: str) -> Dict[str, str]:
    """
    Clear conversation history for a session.

    Use this to start a fresh conversation.
    """
    cleared = chat_assistant.clear_conversation(session_id)
    return {
        "status": "cleared" if cleared else "not_found",
        "session_id": session_id,
    }


@router.get("/assistant/sessions")
async def list_assistant_sessions() -> Dict[str, Any]:
    """
    List all active chat sessions.

    Useful for debugging and session management.
    """
    sessions = []
    for sid, ctx in chat_assistant.conversations.items():
        sessions.append(
            {
                "session_id": sid,
                "message_count": len(ctx.messages),
                "current_equipment": ctx.current_equipment,
                "created_at": ctx.created_at.isoformat(),
            }
        )

    return {
        "sessions": sessions,
        "total": len(sessions),
    }


@router.get("/assistant/info")
async def assistant_info() -> Dict[str, Any]:
    """
    Get Manufacturing Assistant capabilities and usage info.
    """
    return {
        "name": "Manufacturing Analytics Assistant",
        "version": "2.0.0",
        "description": "AI-powered assistant for injection molding analytics (MLX)",
        "capabilities": [
            "Production data queries",
            "Metrics analysis (MTTR, MTBF, efficiency, stability)",
            "SQL query generation",
            "RunRate report summarization",
            "Risk Tower analysis",
            "Anomaly explanation",
            "Troubleshooting assistance",
        ],
        "models": {
            "default": mlx_llm.default_model,
            "reasoning": mlx_llm.reasoning_model,
            "fast": mlx_llm.fast_model,
        },
        "endpoints": {
            "chat": "POST /mlx/assistant/chat",
            "chat_stream": "POST /mlx/assistant/chat/stream",
            "summarize": "POST /mlx/assistant/summarize",
            "explain_anomaly": "POST /mlx/assistant/explain-anomaly",
            "clear_session": "DELETE /mlx/assistant/session/{session_id}",
            "list_sessions": "GET /mlx/assistant/sessions",
        },
        "example_queries": [
            "What is causing high MTTR on equipment EMA-4104?",
            "Generate SQL to find equipment with efficiency below 70%",
            "Explain this Risk Tower report",
            "Why did production drop last Tuesday?",
            "Compare MTBF between plant A and plant B",
        ],
    }
