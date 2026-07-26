"""WebSocket Chat Router for Real-Time LLM Streaming

Provides WebSocket endpoints for streaming chat responses in real-time.

Author: Utku Gulbardak
Date: 2025-12-03
"""

import logging
from typing import Any, Dict

from fastapi import (  # type: ignore[import-untyped]
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from core.cortex_wire import (
    extract_assistant_message,
    extract_text_from_response,
    extract_tool_uses,
    format_text_message,
    format_tool_result,
    get_stop_reason,
)
from core.tools_config import get_tools_for_llm
from services.infrastructure.observability.trace_llm import get_traced_llm_client
from services.infrastructure.scheduler.tool_dispatcher import dispatch_tool_direct

logger = logging.getLogger(__name__)
router = APIRouter()

# Store active WebSocket connections
active_connections: Dict[str, WebSocket] = {}


class ConnectionManager:
    """Manages WebSocket connections for chat."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept and store WebSocket connection."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        """Remove WebSocket connection."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected: {session_id}")

    async def send_message(self, session_id: str, message: Dict[str, Any]):
        """Send message to specific session."""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {e}")
                self.disconnect(session_id)


manager = ConnectionManager()

# Long-running tools that should use async execution
LONG_RUNNING_TOOLS = [
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


def _prepare_claude_messages(
    conversation_history: list, user_message: str
) -> list[Dict[str, Any]]:
    """Prepare messages for Claude API from conversation history and current message.

    Args:
        conversation_history: List of previous conversation messages
        user_message: Current user message

    Returns:
        List of formatted messages for Claude API
    """
    claude_messages = []

    # Add conversation history
    for msg in conversation_history:
        role = msg.get("role")
        if role in ("user", "assistant"):
            claude_messages.append(format_text_message(role, msg.get("content", "")))

    # Add current user message
    claude_messages.append(format_text_message("user", user_message))
    return claude_messages


async def _send_text_response(
    websocket: WebSocket, text_response: str, output_files: Dict[str, Any]
) -> None:
    """Send text response and completion message to client.

    Args:
        websocket: WebSocket connection
        text_response: Text content to send
        output_files: Dictionary of output files
    """
    await websocket.send_json({"type": "text", "content": text_response})
    await websocket.send_json(
        {
            "type": "done",
            "output_files": output_files if output_files else None,
        }
    )


async def _execute_single_tool(
    websocket: WebSocket,
    tool_use: Dict[str, Any],
    output_files: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a single tool and send notifications to client.

    Args:
        websocket: WebSocket connection
        tool_use: Tool use information from LLM
        output_files: Dictionary to update with output files

    Returns:
        Formatted tool result dictionary
    """
    tool_name = tool_use.get("name")
    tool_input = tool_use.get("input", {})
    tool_use_id = tool_use.get("toolUseId")

    # Notify client about tool execution start
    await websocket.send_json(
        {
            "type": "tool_start",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
    )

    # Execute tool directly (no HTTP loopback; LONG_RUNNING_TOOLS may take minutes
    # but awaiting keeps the event loop free for other connections)
    try:
        if tool_name in LONG_RUNNING_TOOLS:
            logger.info("Executing long-running tool over websocket: %s", tool_name)
        result = await dispatch_tool_direct(tool_name, tool_input)

        tool_result = format_tool_result(tool_use_id, result, is_error=False)

        # Check for output files
        if isinstance(result, dict) and "output_files" in result:
            if isinstance(result["output_files"], dict):
                output_files.update(result["output_files"])

        # Notify client about tool execution completion
        await websocket.send_json(
            {
                "type": "tool_end",
                "tool_name": tool_name,
                "status": "success",
                "output_files": output_files if output_files else None,
            }
        )
        return tool_result

    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        error_result = {"error": str(e)}
        tool_result = format_tool_result(tool_use_id, error_result, is_error=True)

        # Notify client about tool execution error
        await websocket.send_json(
            {
                "type": "tool_end",
                "tool_name": tool_name,
                "status": "error",
                "error": str(e),
            }
        )
        return tool_result


async def _handle_tool_use_loop(
    websocket: WebSocket,
    llm_client: Any,
    claude_messages: list,
    session_id: str,
    initial_response: Dict[str, Any],
) -> Dict[str, Any]:
    """Handle the tool use loop with streaming updates.

    Args:
        websocket: WebSocket connection
        llm_client: Active LLM client instance
        claude_messages: Initial messages for Claude
        session_id: Session identifier
        initial_response: Initial response from LLM

    Returns:
        Dictionary with output_files and whether max iterations was reached
    """
    max_iterations = 5
    iteration = 0
    output_files = {}
    response = initial_response

    while iteration < max_iterations:
        stop_reason = get_stop_reason(response)

        # If no tool use, extract and stream text
        if stop_reason != "tool_use":
            text_response = extract_text_from_response(response)
            if text_response:
                await _send_text_response(websocket, text_response, output_files)
            return {"output_files": output_files, "max_iterations_reached": False}

        # Extract tool uses
        tool_uses = extract_tool_uses(response)
        if not tool_uses:
            break

        # Save assistant's tool use message
        assistant_message = extract_assistant_message(response)
        claude_messages.append(assistant_message)

        # Execute each tool
        tool_results = []
        for tool_use in tool_uses:
            tool_result = await _execute_single_tool(websocket, tool_use, output_files)
            tool_results.append(tool_result)
            claude_messages.append(tool_result)

        # Get next response with tool results
        llm_tools = get_tools_for_llm()
        response = llm_client.get_response(
            messages=claude_messages,
            tools=llm_tools,
            session_id=session_id,
        )

        if not response:
            await websocket.send_json(
                {
                    "type": "error",
                    "content": "Failed to get LLM response after tool execution",
                }
            )
            break

        iteration += 1

    return {"output_files": output_files, "max_iterations_reached": True}


async def _process_message(
    websocket: WebSocket, data: Dict[str, Any], session_id: str
) -> None:
    """Process a single chat message from the client.

    Args:
        websocket: WebSocket connection
        data: Message data from client
        session_id: Session identifier
    """
    user_message = data.get("content", "").strip()
    conversation_history = data.get("conversation_history", [])

    if not user_message:
        await websocket.send_json(
            {"type": "error", "content": "Message cannot be empty"}
        )
        return

    # Send acknowledgment
    await websocket.send_json(
        {"type": "ack", "content": "Message received, processing..."}
    )

    try:
        # Initialize Bedrock client (traced if Langfuse is enabled)
        llm_client = get_traced_llm_client()

        # Prepare messages for Claude
        claude_messages = _prepare_claude_messages(conversation_history, user_message)

        # Get initial response
        llm_tools = get_tools_for_llm()
        response = llm_client.get_response(
            messages=claude_messages,
            tools=llm_tools,
            session_id=session_id,
        )

        if not response:
            await websocket.send_json(
                {"type": "error", "content": "Failed to get LLM response"}
            )
            return

        # Handle tool use loop
        result = await _handle_tool_use_loop(
            websocket, llm_client, claude_messages, session_id, response
        )

        # If we hit max iterations
        if result["max_iterations_reached"]:
            await websocket.send_json(
                {
                    "type": "text",
                    "content": "Reached maximum tool use iterations. Response may be incomplete.",
                }
            )
            await websocket.send_json(
                {
                    "type": "done",
                    "status": "partial",
                    "output_files": (
                        result["output_files"] if result["output_files"] else None
                    ),
                }
            )
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "content": f"Error: {str(e)}"})


@router.websocket("/ws/{session_id}")
async def websocket_chat_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time chat streaming.

    Client sends JSON messages:
        {
            "type": "message",
            "content": "What is the ROI for equipment EMA-4104?",
            "conversation_history": []
        }

    Server sends JSON responses:
        {
            "type": "text" | "tool_start" | "tool_end" | "error" | "done",
            "content": "...",
            "tool_name": "...",      // if type is tool_start/tool_end
            "output_files": {...}    // if files were generated
        }
    """
    await manager.connect(websocket, session_id)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            message_type = data.get("type", "message")
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if message_type != "message":
                continue

            await _process_message(websocket, data, session_id)
    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket error for {session_id}: {e}", exc_info=True)
        manager.disconnect(session_id)
