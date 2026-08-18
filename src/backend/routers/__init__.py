"""Router package for Cortex Workflow Agent.

Exposes only the scheduler and MCP routers. The analytics, chat, email, config, and
monitoring routers were removed during the hackathon trim - the agent calls analysis
tools directly via dispatch_tool_direct, not over HTTP.
"""
