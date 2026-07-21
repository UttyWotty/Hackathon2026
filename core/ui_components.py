"""
UI Components for the Streamlit chat interface.

Contains all UI rendering functions and formatting logic.
"""

from typing import Any, Dict

import streamlit as st


def render_page_header():
    """Render the page header and sidebar."""
    st.set_page_config(
        page_title="Manufacturing Analytics AI",
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS
    st.markdown(
        """
    <style>
    .main {padding: 2rem;}
    .stChatMessage {padding: 1rem; border-radius: 0.5rem;}
    .stChatInputContainer {padding: 1rem 0;}
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    """Render the sidebar with information and controls."""
    with st.sidebar:
        st.title("🏭 Manufacturing Analytics")
        st.markdown("---")

        st.subheader("📊 Available Analyses")
        st.markdown("""
        - **RunRate**: MTTR, MTBF, Stop Detection, Efficiency
        - **ROI**: Cost Efficiency, Performance Metrics
        - **Capacity**: OEE, Production Planning, Multi-Target
        """)

        st.markdown("---")
        st.subheader("🌍 Available Schemas")
        st.markdown("""
        Database: **MMS**
        
        **Schemas:**
        - NORDPLAST 
        - ARCWELD 
        - MERIDIAN
        - CALDERA
        - VANTIS
        - ORESUND
        - KESTREL
        - HALLERT
        - OKSNES
        - LINDHOLM
        - SOLVANG
        - TERNA
        - AURELIA
        - FJORDVIK
        
        ⚠️ *All analyses use MASTER_SHOT_TABLE as the single source of truth*
        """)

        st.markdown("---")
        st.subheader("💡 Tips")
        st.markdown("""
        - Mention client name in your query
        - Specify equipment codes clearly
        - Use YYYY-MM-DD date format
        - Can compare across clients
        """)

        st.markdown("---")
        st.caption(f"Session: {st.session_state.get('session_id', 'N/A')}")

        # Clear chat button
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


def render_chat_message(role: str, content: str):
    """
    Render a chat message.

    Args:
        role: Message role (user/assistant)
        content: Message content
    """
    with st.chat_message(role):
        st.markdown(content)


def render_tool_execution(tool_name: str, tool_input: Dict[str, Any]):
    """
    Render tool execution status.

    Args:
        tool_name: Name of the tool being executed
        tool_input: Tool input parameters
    """
    with st.status(f"🔧 Executing: **{tool_name}**", expanded=True) as status:
        st.write("**Parameters:**")
        for key, value in tool_input.items():
            st.write(f"- {key}: `{value}`")
        status.update(label=f"✅ Completed: **{tool_name}**", state="complete")


def render_download_button(
    file_path: str, label: str = "📥 Download Report", key: str = None
):
    """
    Render a download button for generated reports.

    Args:
        file_path: Path to the file
        label: Button label
        key: Unique key for the button (auto-generated from file_path if not provided)
    """
    try:
        with open(file_path, "rb") as file:
            file_data = file.read()
            file_name = file_path.split("/")[-1]

            # Generate unique key from file path if not provided
            if key is None:
                import hashlib

                key = hashlib.md5(file_path.encode()).hexdigest()[:16]

            st.download_button(
                label=label,
                data=file_data,
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=key,
            )
    except Exception as e:
        st.error(f"Error loading file: {e}")


def format_metrics(metrics: Any) -> str:
    """
    Format metrics dictionary or list into readable text.

    Args:
        metrics: Metrics data (dict or list)

    Returns:
        Formatted string
    """
    if not metrics:
        return "No metrics available"

    # Handle list of metrics
    if isinstance(metrics, list):
        if not metrics:
            return "No metrics available"

        if len(metrics) == 1:
            metric_dict = metrics[0]
            formatted = []
            for key, value in metric_dict.items():
                label = key.replace("_", " ").title()

                if isinstance(value, float):
                    if any(
                        x in key.lower() for x in ["percentage", "efficiency", "score"]
                    ):
                        formatted.append(f"• **{label}**: {value:.2f}%")
                    else:
                        formatted.append(f"• **{label}**: {value:,.2f}")
                elif isinstance(value, (int, float)):
                    formatted.append(f"• **{label}**: {value:,}")
                else:
                    formatted.append(f"• **{label}**: {value}")

            return "\n".join(formatted)
        else:
            return f"Multiple metrics returned ({len(metrics)} items)"

    # Handle dictionary
    elif isinstance(metrics, dict):
        formatted = []
        for key, value in metrics.items():
            label = key.replace("_", " ").title()

            if isinstance(value, float):
                if any(x in key.lower() for x in ["percentage", "efficiency", "score"]):
                    formatted.append(f"• **{label}**: {value:.2f}%")
                else:
                    formatted.append(f"• **{label}**: {value:,.2f}")
            elif isinstance(value, (int, float)):
                formatted.append(f"• **{label}**: {value:,}")
            else:
                formatted.append(f"• **{label}**: {value}")

        return "\n".join(formatted)

    return str(metrics)


def display_error(error_message: str):
    """
    Display an error message.

    Args:
        error_message: Error message to display
    """
    st.error(error_message)


def display_success(success_message: str):
    """
    Display a success message.

    Args:
        success_message: Success message to display
    """
    st.success(success_message)


def display_info(info_message: str):
    """
    Display an info message.

    Args:
        info_message: Info message to display
    """
    st.info(info_message)


def display_warning(warning_message: str):
    """
    Display a warning message.

    Args:
        warning_message: Warning message to display
    """
    st.warning(warning_message)
