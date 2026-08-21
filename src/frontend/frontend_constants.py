"""Shared configuration constants for the Streamlit frontend modules.

Holds values that more than one frontend module needs, so that a change to a
Cortex model id or a table name is made in exactly one place. Snowflake retires
Cortex models into a "legacy state" without warning, which previously broke both
the 5 Whys panel and the help chat simultaneously because each hardcoded its own
copy of the model name.
"""

# Cortex model used by every SNOWFLAKE.CORTEX.COMPLETE() call in the frontend.
# Verified available on this account 2026-08-21. Matches CORTEX_MODEL in .env,
# so the dashboard and the backend agent report the same model. The earlier
# value,
# "mistral-large2", was retired by Snowflake and now returns:
#   "The model mistral-large2 has been in legacy state, please use other models."
# Known-good alternatives on this account: llama3.1-70b, llama3.3-70b.
CORTEX_COMPLETE_MODEL: str = "claude-sonnet-4-6"
