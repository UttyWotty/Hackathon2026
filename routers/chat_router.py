"""Chat API Router for LLM Conversations

Provides HTTP endpoints for chat interface integration with full tool execution support.

Author: Utku Gulbardak
Date: 2025-12-03
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from core.cortex_wire import (
    extract_assistant_message,
    extract_text_from_response,
    extract_tool_uses,
    format_text_message,
    format_tool_result,
    get_stop_reason,
)
from core.tools_config import execute_tool, get_tools_for_llm
from services.infrastructure.jobs.job_queue import get_job_queue
from services.infrastructure.observability.trace_llm import get_traced_llm_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Store chat sessions (in production, use Redis or database)
chat_sessions: Dict[str, Dict[str, Any]] = {}


class ChatMessage(BaseModel):
    """Chat message model."""

    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(
        None, description="Session ID for conversation continuity"
    )
    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        None, description="Previous conversation messages"
    )


class ChatResponse(BaseModel):
    """Chat response model."""

    response: str = Field(..., description="AI response text")
    session_id: str = Field(..., description="Session ID")
    tool_executions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Tool executions performed"
    )
    status: str = Field(..., description="Response status (success/partial/error)")
    output_files: Optional[Dict[str, str]] = Field(
        None, description="Generated file paths (excel/ppt)"
    )


@router.post(
    "/message", response_model=ChatResponse, tags=["Chat"], summary="Send Chat Message"
)
async def send_chat_message(
    request: Request,
    chat_request: ChatMessage,
):
    """Send a message to the LLM and get a response with tool execution support.

    This endpoint wraps the LLM conversation logic and exposes it via HTTP API
    so React/other frontends can use it.

    Features:
        - Multi-turn conversations with session management
        - Automatic tool execution (analytics, queries, etc.)
        - File generation tracking (Excel, PowerPoint)
        - Error handling and retry logic

    Example:
        ```json
        {
            "message": "What is the ROI for equipment EMA-4104 in 2024?",
            "session_id": "chat_20251203_130000"
        }
        ```

    Returns:
        ChatResponse with AI response, tool executions, and file URLs
    """
    try:
        user_message = chat_request.message.strip()
        session_id = (
            chat_request.session_id
            or f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        conversation_history = chat_request.conversation_history or []

        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Initialize or get session
        if session_id not in chat_sessions:
            chat_sessions[session_id] = {
                "messages": [],
                "created_at": datetime.now().isoformat(),
            }

        session = chat_sessions[session_id]

        # Initialize the configured LLM client (traced if Langfuse is enabled)
        llm_client = get_traced_llm_client()

        # Prepare messages for Claude (same logic as Streamlit)
        claude_messages = []

        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") in ("user", "assistant"):
                    claude_messages.append(
                        format_text_message(msg["role"], msg.get("content", ""))
                    )
        else:
            # Use session history
            for msg in session["messages"]:
                if msg["role"] == "user":
                    claude_messages.append(format_text_message("user", msg["content"]))
                elif msg["role"] == "assistant":
                    if "_full_conversation" in msg:
                        for conv_msg in msg["_full_conversation"]:
                            claude_messages.append(conv_msg)
                    claude_messages.append(
                        format_text_message("assistant", msg["content"])
                    )

        # Add current user message
        claude_messages.append(format_text_message("user", user_message))

        # Save user message to session
        session["messages"].append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Get tools for the active backend
        llm_tools = get_tools_for_llm()

        # Get initial response
        response = llm_client.get_response(
            messages=claude_messages,
            tools=llm_tools,
            session_id=session_id,
        )

        if not response:
            raise HTTPException(status_code=500, detail="Failed to get LLM response")

        # Handle tool use loop (same logic as Streamlit)
        max_iterations = 5
        iteration = 0
        full_conversation = []
        tool_executions = []
        output_files = {}

        while iteration < max_iterations:
            stop_reason = get_stop_reason(response)

            # If no tool use, extract and return text
            if stop_reason != "tool_use":
                text_response = extract_text_from_response(response)
                if text_response:
                    # Save assistant message to session
                    if full_conversation:
                        session["messages"].append(
                            {
                                "role": "assistant",
                                "content": text_response,
                                "_full_conversation": full_conversation
                                + [extract_assistant_message(response)],
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    else:
                        session["messages"].append(
                            {
                                "role": "assistant",
                                "content": text_response,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    return ChatResponse(
                        response=text_response,
                        session_id=session_id,
                        tool_executions=tool_executions,
                        status="success",
                        output_files=output_files if output_files else None,
                    )
                break

            # Extract tool uses
            tool_uses = extract_tool_uses(response)
            if not tool_uses:
                break

            # Save assistant's tool use message
            assistant_message = extract_assistant_message(response)
            full_conversation.append(assistant_message)

            # Execute each tool
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.get("name")
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use.get("toolUseId")

                # Track tool execution
                tool_exec = {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "status": "executing",
                    "tool_use_id": tool_use_id,
                }
                tool_executions.append(tool_exec)

                # Execute tool (same logic as Streamlit)
                try:
                    long_running_tools = [
                        "run_capacity_analysis",
                        "run_runrate_analysis",
                        "run_roi_analysis",
                        "run_rca_analysis",
                        "run_ct_efficiency_analysis",
                        "run_ct_deviation_analysis",
                        "run_tooling_eol_analysis",
                        "refresh_master_shot_table",
                        "generate_presentation",
                        "generate_weekly_comparison_ppt",
                    ]

                    if tool_name in long_running_tools:
                        # Submit job for async execution directly using job queue
                        # This avoids HTTP timeout issues by not making HTTP calls to ourselves
                        try:
                            # Use the same executor function as mcp_router
                            async def _execute_tool_async_wrapper(
                                tool_name: str, arguments: Dict[str, Any]
                            ) -> Dict[str, Any]:
                                """Async wrapper for tool execution."""
                                from services.infrastructure.scheduler.tool_dispatcher import (
                                    dispatch_tool_direct,
                                )

                                try:
                                    result = await dispatch_tool_direct(
                                        tool_name, arguments
                                    )
                                    return result
                                except Exception as e:
                                    logger.error(
                                        f"Error executing tool {tool_name}: {e}",
                                        exc_info=True,
                                    )
                                    return {
                                        "status": "error",
                                        "error": str(e),
                                    }

                            # Submit job directly to queue (non-blocking, no HTTP call)
                            job_queue = get_job_queue()
                            job_id = await job_queue.submit_job(
                                tool_name=tool_name,
                                arguments=tool_input,
                                executor_func=_execute_tool_async_wrapper,
                            )

                            if job_id:
                                # Return job_id for frontend to poll
                                result = {
                                    "status": "pending",
                                    "job_id": job_id,
                                    "message": f"Analysis started. Use /tools/jobs/{job_id} to check status.",
                                    "poll_url": f"/tools/jobs/{job_id}",
                                }
                                tool_exec["status"] = "pending"
                                tool_exec["job_id"] = job_id
                                logger.info(f"Job submitted: {job_id} for {tool_name}")
                            else:
                                raise Exception("Failed to get job_id from queue")
                        except Exception as e:
                            logger.error(
                                f"Failed to submit async job: {e}", exc_info=True
                            )
                            raise Exception(f"Failed to submit job: {str(e)}")
                    else:
                        # Synchronous execution for quick operations
                        result = execute_tool(tool_name, tool_input)
                        tool_exec["status"] = "success"
                        tool_exec["result"] = result

                    tool_results.append(
                        format_tool_result(tool_use_id, result, is_error=False)
                    )

                    # Check for output files (only if result is complete, not pending)
                    if isinstance(result, dict) and result.get("status") != "pending":
                        if "output_files" in result:
                            if isinstance(result["output_files"], dict):
                                output_files.update(result["output_files"])
                except Exception as e:
                    logger.error(f"Tool execution error: {e}", exc_info=True)
                    error_result = {"error": str(e)}
                    tool_results.append(
                        format_tool_result(tool_use_id, error_result, is_error=True)
                    )
                    tool_exec["status"] = "error"
                    tool_exec["error"] = str(e)

            # Check if we have pending jobs (async operations that need polling)
            has_pending_jobs = any(
                tool_exec.get("status") == "pending"
                or (
                    isinstance(tool_exec.get("result"), dict)
                    and tool_exec.get("result", {}).get("status") == "pending"
                )
                for tool_exec in tool_executions
            )

            # If we have pending jobs, return early with job_ids for frontend to poll
            if has_pending_jobs:
                logger.info(
                    f"Returning early with {len(tool_executions)} pending job(s) for polling"
                )
                return ChatResponse(
                    response="Analysis started. Processing in background. Please wait...",
                    session_id=session_id,
                    tool_executions=tool_executions,
                    status="pending",
                    output_files=None,
                )

            # Save tool results to conversation
            for tool_result in tool_results:
                full_conversation.append(tool_result)

            # Append to claude_messages for next API call
            claude_messages.append(assistant_message)
            for tool_result in tool_results:
                claude_messages.append(tool_result)

            # Get next response with tool results
            llm_tools = get_tools_for_llm()
            response = llm_client.get_response(
                messages=claude_messages,
                tools=llm_tools,
                session_id=session_id,
            )

            if not response:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get LLM response after tool execution",
                )

            iteration += 1

        # If we hit max iterations
        if iteration >= max_iterations:
            return ChatResponse(
                response="Reached maximum tool use iterations. Response may be incomplete.",
                session_id=session_id,
                tool_executions=tool_executions,
                status="partial",
                output_files=output_files if output_files else None,
            )

        return ChatResponse(
            response="",
            session_id=session_id,
            tool_executions=tool_executions,
            status="success",
            output_files=output_files if output_files else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.get("/session/{session_id}", tags=["Chat"], summary="Get Chat Session")
async def get_chat_session(session_id: str):
    """Get chat session history.

    Returns all messages in a session for continuity across page refreshes.
    """
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return chat_sessions[session_id]


@router.delete("/session/{session_id}", tags=["Chat"], summary="Delete Chat Session")
async def delete_chat_session(session_id: str):
    """Delete a chat session.

    Clears all conversation history for privacy or to start fresh.
    """
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions", tags=["Chat"], summary="List All Sessions")
async def list_sessions():
    """List all active chat sessions.

    Useful for debugging or session management.
    """
    return {
        "sessions": [
            {
                "session_id": sid,
                "created_at": data.get("created_at"),
                "message_count": len(data.get("messages", [])),
            }
            for sid, data in chat_sessions.items()
        ],
        "total": len(chat_sessions),
    }


@router.get("/", tags=["Chat"], summary="Chat Service Info")
async def chat_info():
    """Get information about the chat service."""
    return {
        "service": "Chat Service",
        "status": "running",
        "version": "1.0.0",
        "description": "Multi-turn chat with tool execution (REST + MCP tools)",
        "endpoints": {
            "send_message": "POST /chat/message",
            "get_session": "GET /chat/session/{session_id}",
            "delete_session": "DELETE /chat/session/{session_id}",
            "list_sessions": "GET /chat/sessions",
        },
        "features": [
            "Multi-turn conversations",
            "Tool execution (analytics, queries, etc.)",
            "File generation (Excel, PowerPoint)",
            "Session persistence",
            "Error handling and retry logic",
        ],
        "active_sessions": len(chat_sessions),
    }
