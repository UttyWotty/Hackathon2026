"""
Manufacturing Analytics AI Chat Interface (Refactored)

A Streamlit-based web interface for interacting with manufacturing analytics
using Claude via AWS Bedrock.

Author: Utku Gulbardak
Date: 2025-10-29
"""

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import from modular components
from core.cortex_wire import (  # noqa: E402
    extract_assistant_message,
    extract_text_from_response,
    extract_tool_uses,
    format_text_message,
    format_tool_result,
    get_stop_reason,
)
from core.llm_backend import get_llm_client  # noqa: E402
from core.prompts import get_error_message, get_welcome_message  # noqa: E402
from core.tools_config import execute_tool, get_tools_for_llm  # noqa: E402
from core.ui_components import (  # noqa: E402
    display_error,
    render_chat_message,
    render_download_button,
    render_page_header,
    render_sidebar,
    render_tool_execution,
)

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment variables from {env_path}")
else:
    print(f"⚠️  Environment file not found at {env_path}")


# Initialize page
render_page_header()


# Initialize session state
def initialize_session():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        from datetime import datetime

        st.session_state.session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if "llm_client" not in st.session_state:
        st.session_state.llm_client = get_llm_client()


initialize_session()


# Render sidebar
render_sidebar()


# Main chat interface
st.title("🏭 Manufacturing Analytics AI")


# Display welcome message on first load
if len(st.session_state.messages) == 0:
    with st.chat_message("assistant"):
        st.markdown(get_welcome_message())


# Display chat history
for message in st.session_state.messages:
    render_chat_message(message["role"], message["content"])


# Handle user input
if prompt := st.chat_input("Ask a question about manufacturing analytics..."):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    render_chat_message("user", prompt)

    # Process with Claude
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Prepare messages for Claude
            claude_messages = []
            for msg in st.session_state.messages:
                if msg["role"] == "user":
                    claude_messages.append(format_text_message("user", msg["content"]))
                elif msg["role"] == "assistant":
                    # Check if this message has full conversation history (tool uses + results)
                    if "_full_conversation" in msg:
                        # Restore the complete conversation including tool uses
                        for conv_msg in msg["_full_conversation"]:
                            claude_messages.append(conv_msg)
                        # Add the final text response
                        if msg["content"] and not msg["content"].startswith("["):
                            claude_messages.append(
                                format_text_message("assistant", msg["content"])
                            )
                    else:
                        # Simple text response without tools
                        claude_messages.append(
                            format_text_message("assistant", msg["content"])
                        )

            # Get response from Claude
            response = st.session_state.llm_client.get_response(
                messages=claude_messages,
                tools=get_tools_for_llm(),
                session_id=st.session_state.session_id,
            )

            if not response:
                error_msg = get_error_message("api")
                display_error(error_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_msg}
                )
                st.stop()

            # Handle tool use loop
            # IMPORTANT: We track the full conversation (tool uses + results) to preserve
            # context across Streamlit reruns. Without this, downloading files or any page
            # rerun would lose the tool execution history, causing the LLM to repeat analyses.
            max_iterations = 5
            iteration = 0
            full_conversation = []  # Track complete conversation including tool uses

            while iteration < max_iterations:
                stop_reason = get_stop_reason(response)

                # If no tool use, extract and display text
                if stop_reason != "tool_use":
                    text_response = extract_text_from_response(response)
                    if text_response:
                        st.markdown(text_response)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": text_response}
                        )
                        # If we had tool uses, also save the final response to full_conversation
                        if full_conversation:
                            full_conversation.append(
                                extract_assistant_message(response)
                            )
                    break

                # Extract tool uses
                tool_uses = extract_tool_uses(response)
                if not tool_uses:
                    break

                # Save assistant's tool use message to conversation history
                assistant_message = extract_assistant_message(response)
                full_conversation.append(assistant_message)

                # Execute each tool
                tool_results = []
                for tool_use in tool_uses:
                    tool_name = tool_use.get("name")
                    tool_input = tool_use.get("input", {})
                    tool_use_id = tool_use.get("toolUseId")

                    # Show tool execution status
                    render_tool_execution(tool_name, tool_input)

                    # Execute tool
                    try:
                        result = execute_tool(tool_name, tool_input)
                        tool_results.append(
                            format_tool_result(tool_use_id, result, is_error=False)
                        )

                        # If result has output files, offer download
                        if isinstance(result, dict) and "output_files" in result:
                            output_files = result["output_files"]
                            if isinstance(output_files, dict):
                                if "excel" in output_files:
                                    render_download_button(
                                        output_files["excel"],
                                        "📥 Download Excel Report",
                                    )

                    except Exception as e:
                        error_result = {"error": str(e)}
                        tool_results.append(
                            format_tool_result(tool_use_id, error_result, is_error=True)
                        )

                # Save tool results to conversation history
                for tool_result in tool_results:
                    full_conversation.append(tool_result)

                # Append to claude_messages for next API call
                claude_messages.append(assistant_message)
                for tool_result in tool_results:
                    claude_messages.append(tool_result)

                # Get next response with tool results
                response = st.session_state.llm_client.get_response(
                    messages=claude_messages,
                    tools=get_tools_for_llm(),
                    session_id=st.session_state.session_id,
                )

                if not response:
                    error_msg = get_error_message("api")
                    display_error(error_msg)
                    # Save what we have so far to session state
                    if full_conversation:
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": "[Tool execution completed but response generation failed]",
                                "_full_conversation": full_conversation,
                            }
                        )
                    break

                iteration += 1

            # Save the complete conversation to session state
            # This ensures tool executions are preserved across reruns
            if full_conversation and iteration < max_iterations:
                # Get the final text response
                final_text = extract_text_from_response(response)
                if final_text:
                    # Remove the already-added final message and replace with complete history
                    if (
                        st.session_state.messages
                        and st.session_state.messages[-1]["role"] == "assistant"
                    ):
                        st.session_state.messages[-1][
                            "_full_conversation"
                        ] = full_conversation

            # Check if we hit max iterations
            if iteration >= max_iterations:
                st.warning(
                    "⚠️ Reached maximum tool use iterations. Response may be incomplete."
                )
                # Save conversation history even if incomplete
                if full_conversation:
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": "[Analysis incomplete - max iterations reached]",
                            "_full_conversation": full_conversation,
                        }
                    )


# Footer
st.markdown("---")
st.caption(
    f"Session ID: {st.session_state.session_id} | Manufacturing Analytics AI v1.0"
)
