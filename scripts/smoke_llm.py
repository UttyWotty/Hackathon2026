"""
End-to-end smoke test for the configured LLM backend.

Makes one real call through the full stack - backend factory, tool conversion,
transport, and response parsing - and reports what came back. Use it to prove
the agent loop's wiring against MLX locally or Cortex once an account exists.

Usage:
    python scripts/smoke_llm.py            # uses LLM_BACKEND from .env
    python scripts/smoke_llm.py mlx        # force the local MLX backend
    python scripts/smoke_llm.py cortex     # force Snowflake Cortex
    python scripts/smoke_llm.py mlx 3      # send only 3 tools, not all 35

The tool count matters on local models: all 35 schemas are about 7,000 tokens
of prefill on top of a 4,400-token system prompt, which a quantized 32B can
take minutes to chew through. Trim it to prove the wiring, then raise it.
"""

import json
import sys
from pathlib import Path

# Allow running as a plain script from the repository root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.cortex_errors import CortexError  # noqa: E402
from core.cortex_wire import (  # noqa: E402
    extract_text_from_response,
    extract_tool_uses,
    get_stop_reason,
)
from core.llm_backend import LLM_BACKEND, get_llm_client  # noqa: E402
from core.tools_config import get_tools_for_llm  # noqa: E402

PROMPT = "Which machines show cycle time drift? Use the available tools."
SEPARATOR = "-" * 60
# Rough bytes-per-token ratio, good enough for a size warning.
CHARS_PER_TOKEN = 4
EXIT_OK = 0
EXIT_FAILED = 1


def main() -> int:
    """Run one call against the selected backend and print a verdict."""
    backend = sys.argv[1] if len(sys.argv) > 1 else LLM_BACKEND
    print(SEPARATOR, flush=True)
    print(f"backend : {backend}", flush=True)

    try:
        client = get_llm_client(backend)
    except CortexError as exc:
        print(f"FAILED  : could not build the client\n          {exc}", flush=True)
        return EXIT_FAILED

    tools = get_tools_for_llm()
    if len(sys.argv) > 2:
        tools = tools[: int(sys.argv[2])]

    payload_tokens = len(json.dumps(tools)) // CHARS_PER_TOKEN
    print(f"model   : {getattr(client, 'model', 'unknown')}", flush=True)
    print(f"url     : {getattr(client, 'url', 'unknown')}", flush=True)
    print(f"tools   : {len(tools)} (~{payload_tokens:,} tokens of schema)", flush=True)
    print(SEPARATOR, flush=True)
    print("calling... (local models prefill slowly; this can take minutes)", flush=True)

    response = client.get_response([{"role": "user", "content": PROMPT}], tools=tools)

    if response is None:
        print(
            "FAILED  : the client returned None. The request did not succeed.",
            flush=True,
        )
        print(
            "          The logged error above says whether it timed out or", flush=True
        )
        print(
            "          could not connect. On timeout, retry with fewer tools.",
            flush=True,
        )
        return EXIT_FAILED

    stop_reason = get_stop_reason(response)
    text = extract_text_from_response(response)
    tool_uses = extract_tool_uses(response)

    print(f"stop    : {stop_reason}", flush=True)
    print(f"text    : {text[:300] if text else '(none)'}", flush=True)
    print(f"calls   : {len(tool_uses)}", flush=True)
    for use in tool_uses:
        print(
            f"          -> {use['name']}({use['input']}) id={use['toolUseId']}",
            flush=True,
        )
    print(SEPARATOR, flush=True)

    if stop_reason == "tool_use" and tool_uses:
        print(
            "OK      : full chain works - tools converted, called, and parsed.",
            flush=True,
        )
    elif text:
        print("PARTIAL : the model replied but called no tool.", flush=True)
        print(
            "          Wiring is proven; tool selection is a model-quality issue.",
            flush=True,
        )
    else:
        print("FAILED  : response carried neither text nor a tool call.", flush=True)
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
