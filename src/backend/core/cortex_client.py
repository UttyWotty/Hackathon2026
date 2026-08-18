"""
Snowflake Cortex Messages API client, the Bedrock replacement for the agent loop.

Owns the single HTTP call to POST /api/v2/cortex/v1/messages authenticated with a
Snowflake Programmatic Access Token, delegating all payload construction and
response parsing to the pure cortex_wire module. The transport is injectable so
the client can be exercised in tests without a network or an account.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .cortex_errors import CortexConfigurationError, CortexRequestError
from .cortex_wire import build_messages_payload
from .http_transport import Transport, post_json
from .prompts import get_system_prompt
from .token_tracker import get_token_tracker

logger = logging.getLogger(__name__)

# Credentials. Empty defaults keep import side-effect free; absence is reported
# by the constructor rather than at import time.
SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT", "")
SNOWFLAKE_PAT = os.getenv("SNOWFLAKE_PAT", "")

# The model id is account- and region-specific. Confirm with
# SHOW CORTEX BASE MODELS before the first run rather than trusting this default.
CORTEX_MODEL = os.getenv("CORTEX_MODEL", "claude-sonnet-4-5")

CORTEX_TIMEOUT_SECONDS = int(os.getenv("CORTEX_TIMEOUT_SECONDS", "60"))
CORTEX_ENABLE_PROMPT_CACHING = (
    os.getenv("CORTEX_ENABLE_PROMPT_CACHING", "true").lower() == "true"
)

# Wire constants from the verified request shape (HACKATHON_PLAN.md, A.1).
ANTHROPIC_VERSION = "2023-06-01"
TOKEN_TYPE_HEADER = "X-Snowflake-Authorization-Token-Type"
TOKEN_TYPE_PAT = "PROGRAMMATIC_ACCESS_TOKEN"
MESSAGES_PATH = "/api/v2/cortex/v1/messages"
HOST_TEMPLATE = "https://{account}.snowflakecomputing.com"

# Defaults for get_response, matching the BedrockClient signature it replaces.
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
DEFAULT_SESSION_ID = "default"
DEFAULT_OPERATION = "chat_interface"


class CortexClient:
    """Client for Snowflake Cortex Claude interactions over the Messages API."""

    # Recorded on every decision trail, so a run is never ambiguous about
    # whether Cortex or a local development model did the reasoning.
    backend_name = "cortex"

    def __init__(
        self,
        account: Optional[str] = None,
        pat: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = CORTEX_TIMEOUT_SECONDS,
        enable_prompt_caching: bool = CORTEX_ENABLE_PROMPT_CACHING,
        transport: Optional[Transport] = None,
    ) -> None:
        """
        Initialise the Cortex client.

        Args:
            account: Account identifier such as "myorg-myacct". Defaults to
                the SNOWFLAKE_ACCOUNT environment variable.
            pat: Programmatic Access Token. Defaults to SNOWFLAKE_PAT.
            model: Cortex model id. Defaults to CORTEX_MODEL.
            timeout_seconds: Per-request timeout. Defaults to CORTEX_TIMEOUT_SECONDS.
            enable_prompt_caching: Attach an ephemeral cache breakpoint to the
                system block. Defaults to CORTEX_ENABLE_PROMPT_CACHING.
            transport: Injected transport callable. Defaults to requests.

        Raises:
            CortexConfigurationError: If the account identifier or PAT is absent.
        """
        self.account = account or os.getenv("SNOWFLAKE_ACCOUNT", "")
        self.pat = pat or os.getenv("SNOWFLAKE_PAT", "")
        self.model = model or os.getenv("CORTEX_MODEL", CORTEX_MODEL)
        self.timeout_seconds = timeout_seconds
        self.enable_prompt_caching = enable_prompt_caching
        self.transport = transport or post_json

        if not self.account:
            raise CortexConfigurationError(
                "No Snowflake account identifier. Set SNOWFLAKE_ACCOUNT "
                "(for example 'myorg-myacct') or pass account=."
            )
        if not self.pat:
            raise CortexConfigurationError(
                "No Snowflake PAT. Set SNOWFLAKE_PAT or pass pat=. A PAT also "
                "requires a network policy on the account before it will work."
            )

        self.url = HOST_TEMPLATE.format(account=self.account) + MESSAGES_PATH
        logger.info("Cortex client initialised: model=%s", self.model)

    def _headers(self) -> Dict[str, str]:
        """Build the request headers, including PAT bearer auth."""
        return {
            "Authorization": f"Bearer {self.pat}",
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
            TOKEN_TYPE_HEADER: TOKEN_TYPE_PAT,
        }

    def _track(self, response: Dict[str, Any], session_id: str) -> None:
        """Record token usage, never letting telemetry break the agent loop."""
        usage = response.get("usage", {})
        try:
            get_token_tracker().track_usage(
                model_id=self.model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                operation=DEFAULT_OPERATION,
                session_id=session_id,
            )
        except Exception:  # noqa: BLE001 - telemetry must not break chat
            logger.warning("Token tracking failed for session %s", session_id)

    def get_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a response from Claude via Snowflake Cortex.

        Signature and None-on-failure behaviour match BedrockClient.get_response,
        so the three call sites and the Langfuse tracing proxy are unchanged.

        Args:
            messages: Conversation turns in Anthropic format.
            tools: Tool definitions from get_tools_for_cortex, or None.
            max_tokens: Maximum tokens to generate. Defaults to 4096.
            temperature: Sampling temperature. Defaults to 0.7.
            session_id: Session identifier for token tracking.

        Returns:
            The parsed Cortex response, or None if the request failed.
        """
        payload = build_messages_payload(
            messages=messages,
            system_prompt=get_system_prompt(),
            tools=tools,
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_prompt_caching=self.enable_prompt_caching,
        )

        try:
            response = self.transport(
                self.url, self._headers(), payload, self.timeout_seconds
            )
        except CortexRequestError:
            logger.exception("Cortex call failed for model %s", self.model)
            return None

        self._track(response, session_id)
        return response
