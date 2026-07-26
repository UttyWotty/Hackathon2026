"""
Prompt construction for the autonomous workflow agent.

Builds the instruction and observation block that turns the shared chat system
prompt into a headless operator: one that must decide severity from findings,
act through tools, and stop rather than converse. Pure string assembly, no I/O.
"""

from typing import List

# The agent runs unattended, so the prompt has to close off the failure modes a
# human turn would otherwise catch: asking a question nobody will answer, or
# calling tools forever.
AGENT_INSTRUCTIONS = """You are running as an autonomous manufacturing workflow agent.
There is no human in this conversation and no one will answer a question.

You have been given the results of an automated anomaly sweep. Your job:

1. Judge which findings are genuinely abnormal. Some machines are healthy and
   must not be flagged; a false positive is a real cost.
2. Reason across metrics, not one at a time. A machine can look healthy on run
   rate while drifting badly on cycle time deviation. Trends matter more than a
   single reading.
3. For anything you judge abnormal, use the available tools to investigate the
   root cause and produce a report.
4. When you have finished acting, reply with a plain text summary naming the
   equipment you flagged, the severity, and what you did about it.

Do not ask for confirmation. Do not call a tool without a reason you can state.
If nothing is abnormal, say so plainly and call no tools."""

OBSERVATION_HEADER = "Automated sweep results:"
CLOSING_REQUEST = (
    "Decide what is abnormal and act. Finish with your summary as plain text."
)


def build_agent_prompt(findings_text: str) -> str:
    """
    Assemble the single user turn that starts an autonomous run.

    Args:
        findings_text: The condensed sense-phase observations.

    Returns:
        The complete prompt text.
    """
    return "\n\n".join(
        [
            AGENT_INSTRUCTIONS,
            OBSERVATION_HEADER,
            findings_text,
            CLOSING_REQUEST,
        ]
    )


def build_failure_note(failed_tools: List[str]) -> str:
    """
    Describe sense analyses that failed, so the model does not assume silence.

    Args:
        failed_tools: Names of analyses that did not succeed.

    Returns:
        A note for the prompt, or an empty string when everything succeeded.
    """
    if not failed_tools:
        return ""
    return (
        "Note: these analyses failed and their signal is missing, so absence of "
        f"a finding from them proves nothing: {', '.join(failed_tools)}."
    )
