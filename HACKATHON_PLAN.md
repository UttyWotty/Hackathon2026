# Snowflake CoCo CLI Hackathon 2026 - Build Plan

This document is the ready-to-start plan for entering the Snowflake CoCo (Cortex Code) CLI Hackathon 2026 by reusing the manufacturing-api repo as an Intelligent Workflow Automation Agent. It captures the locked decisions, the reuse map, the Bedrock-to-Cortex port strategy, a phased schedule against the Aug 2 2026 deadline, and the pre-build checklist. It is a staging artifact: it lives in the production repo for reference but the actual build happens in a separate sanitized fork.

Revision note (2026-07-22): build status brought current. Phases 1-3 are substantially built in the working tree - the fork and trimmed demo surface, the Bedrock-to-Cortex port behind a backend factory (with an MLX local stand-in), and the autonomous controller with a decision trail. 698 tests pass. Phase 4 (live-account first contact, demo, Cortex Analyst surface, submission) is what remains. The "Not building yet" note in section 1 and the "no build has started" status in section 2 are superseded; per-phase status lines are inline below. See `readme.md` Status for the current summary.

Revision note (2026-07-21): sections 2, 5, 7a, 7b, A.3 and A.4 were corrected against the official hackathon terms and current Snowflake docs. The material changes: the contest supplies the Snowflake account (it was never blocked on the CTO), and Claude Sonnet is not natively available in any AWS APJ region, which reverses the earlier region guidance.

## 1. Locked decisions (2026-07-16)

- Track: Intelligent Workflow Automation Agent (sense anomalies, reason over them, autonomously trigger multi-step workflows).
- Codebase: fresh sanitized fork with synthetic data in a Snowflake trial/hackathon account. The production repo, real credentials, and real client schemas (NORDPLAST, VANTIS, etc.) must never enter the submission or its git history.
- LLM: port from AWS Bedrock (Claude) to Snowflake Cortex (Claude native). Done - see the
  2026-07-22 revision note; the Cortex client and adapter are built behind a backend factory.

## 2. Timeline (source: hackathon brief)

- Registration and submission window: Jun 15 - Aug 2 2026 (per the official terms; the earlier Jul 13 date was wrong).
- Portal closes: Aug 2 2026.
- Final shortlist: Aug 24 2026. Grand finale / demo day: Sep 1-4 2026. Contest period runs through Sep 4.

Status at 2026-07-22: Phases 1-3 are substantially built (see the revision note at the top); Phase 4 and live-account first contact remain. The section 8 cut lines held in practice - the build took Path A own-the-loop and has not yet added Cortex Agents or Cortex Analyst. (The 2026-07-21 reading of "no build has started, 12 days remaining" is superseded.)

Trial account lifetime is a scheduling constraint in its own right. A trial is 30 days from signup, so one started on 2026-07-21 expires around Aug 20 - before both the Aug 24 shortlist and the Sep 1-4 finale. The terms state finalists may be issued a fresh sign-up link if theirs expired, so this is recoverable, but the demo environment must be reproducible from scratch (scripted DDL plus the synthetic data generator) rather than hand-built in an account that will die.

Implication: scope a trimmed, demo-complete prototype, not a product.

## 3. Concept: the autonomous manufacturing workflow agent

A headless controller runs on a trigger (schedule or anomaly event), not a human chat turn:

1. Sense: run anomaly-detection analyses over synthetic manufacturing data.
2. Reason: Cortex (Claude) evaluates severity and likely root cause over the findings.
3. Act: the agent autonomously chains multi-step actions (root-cause analysis, report generation, email notification, scheduling a follow-up).
4. Log: every decision and action is recorded to a visible decision trail for the demo.

A secondary interactive surface lets a user query the same data in natural language (Cortex Analyst) and watch the agent reason and act.

## 4. Reuse map (what ports from this repo)

Sense (anomaly detection):
- run_ct_deviation_analysis, run_rca_analysis, run_ct_efficiency_analysis, find_top_movers, get_plant_health_snapshot, data_quality_audit, validate_approved_cts.

Reason (the agent loop):
- The 35-tool agentic loop and the execute_tool / tool_dispatcher dispatcher (core/tools, services/infrastructure/scheduler/tool_dispatcher.py). The loop shape is LLM-agnostic; only the client changes.

Act (multi-step actions):
- send_email_report, generate_presentation, generate_weekly_comparison_ppt, schedule_job, refresh_master_shot_table, save_insight.

Orchestrate:
- services/infrastructure/scheduler/ (background_scheduler.py, job_service.py, job_result_handler.py) and services/infrastructure/jobs/job_queue.py.

Foundation:
- Snowflake session pool (services/infrastructure/snowflake/session_pool.py), unified cache, FastAPI skeleton with graceful router registration, Streamlit chat UI (core/chat_interface.py), MCP support.

## 5. Cortex port strategy

The entire LLM surface to replace is small: core/llm_client.py (BedrockClient, ~257 lines) plus four parser helpers (extract_text_from_response, extract_tool_uses, get_stop_reason, format_tool_result), consumed by only three files (core/chat_interface.py, routers/chat_router.py, routers/websocket_chat.py). Tool definitions carry a bedrock_adapter.py that formats tool JSON; it gets a Cortex sibling.

Two API paths (both GA as of research on 2026-07-16):

- Path A - Cortex REST inference `/api/v2/cortex/v1/messages` (Anthropic-style). Maps 1:1 to current Bedrock converse payloads and tool schemas. You keep the client-driven loop. Lowest-friction port, maximum loop control.
- Path B - Cortex Agents `agent:run` (GA 2025-11-04). Snowflake owns the orchestration loop server-side and natively bundles Cortex Analyst (text-to-SQL) and Cortex Search. Custom tools can execute client-side, which lets the existing execute_tool dispatcher be reused without rewriting tools as stored procedures.

Recommended hybrid:
- Autonomous controller on Path A - deterministic, observable, easy to log for the demo.
- Interactive "ask the data" surface on Path B with Cortex Analyst - the Snowflake-native flagship showcase judges reward.
Both reuse the existing tool dispatcher.

Model: a GA Claude Sonnet natively available in the account region, which in practice means provisioning the account in AWS us-west-2 or us-east-1 (see A.4). Avoid preview models. Auth: Programmatic Access Token (PAT) as a Bearer header.

Enable prompt caching on the Cortex Messages calls early rather than as an optimisation pass. Cached input reads at 0.15 credits per million tokens against 1.80 uncached, and the agent loop resends a large stable prefix (system prompt plus the tool schema) on every turn, which is exactly the shape that benefits. This matters because of the trial throttle described in 7a, not because of the total credit budget.

## 6. Phased schedule (originally scoped at ~17 days; 12 remain as of 2026-07-21)

The per-phase estimates below are unchanged from the original scoping and total 12-16 days. Against the 12 days actually remaining, the plan only fits at its lower bound with no slippage, which is why section 2 makes the section 8 cut lines the default scope. Phase 4's buffer is the first thing to protect, not the first thing to spend.

Phase 0 - De-risk: complete. Cortex tool-calling and Agents capability, the client-side custom-tool flow, and copy-ready code shapes are confirmed. Outcome: feasible, GA, no technical blockers. The remaining Phase 0 unknown is the account's exact GA Claude model id, which resolves in one query once the account exists (7a).

Phase 1 - Sanitized fork + synthetic data (2-3 days) - DONE (CSV/local path; live-account load untested):
- Fresh git init (no production .env in history; add it to .gitignore before the first commit, not after). Trim to the demo surface: session pool, tool loop, scheduler/jobs, sense/act tools, Streamlit UI. Drop unrelated routers and features.
- Load the synthetic dataset. The generator is already written and tested (see 7c), so this phase is running `python -m synthetic_data.generate --load` against the hackathon account and verifying the sense tools return the planted findings, not authoring a generator. The PUT and COPY INTO path is written but has never run against a live account, so budget time for that first contact.

Phase 2 - Bedrock to Cortex (3-4 days) - DONE (built and unit-tested; not yet run against a live Cortex endpoint):
- Rewrite core/llm_client.py get_response against Path A (`/messages`) with PAT auth; keep the four parser helpers' contracts stable so the loop is untouched. Add a Cortex tool-format adapter beside bedrock_adapter.py. Only three call sites.

Phase 3 - Autonomous controller + Cortex-native surface (4-5 days) - controller DONE, Cortex Analyst surface NOT STARTED:
- Headless sense-decide-act loop triggered by the existing scheduler; Cortex reasons over anomaly findings and chains actions; persist a decision log. DONE - `services/workflow/` plus `models/decision_trail.py` and `scripts/run_agent.py`. Beyond the plan: three agent skills, a shift-notes search surface, and the Risk Tower detector were added.
- Add a Cortex Analyst semantic model over the synthetic schema for the interactive NL-query surface. NOT STARTED (a section 8 cut-line candidate).

Phase 4 - Demo and submission (3-4 days) - demo app DONE (offline only); video and writeup NOT STARTED:
- Streamlit demo: the agent autonomously catches a seeded CT-deviation anomaly and fires the workflow end to end, plus a decision-log view. DONE - `demo/` plus `start_demo.sh`. Three tabs: trigger a live headless run and see it graded against ground truth, browse any past run's trail grouped into sense/reason/act, and the six-week drift chart that shows EMA-4103 climbing 1.9 to 24.0 percent while the fleet holds flat at about 2. The score card reads act-step payloads and flags anything the summary claimed without a backing step.
- Not yet done: every demo run so far has reasoned on the local MLX backend against generated CSVs. The demo has never been driven end to end on Cortex, which is the run the video has to show. That is gated on the account (7a-7d), not on this app.
- Record demo video and writeup. Buffer to Aug 2.

## 7. Pre-build checklist (do before Day 1)

### 7a. Account provisioning (self-service, corrected 2026-07-21)

This was previously listed as an owner-action blocker requiring the CTO. That was wrong. The official contest terms state the sponsor provides a free Trial Account to registrants with a 400 USD credit, self-served through a sign-up link on the contest site. No credentials need to be shared by anyone, and production credentials must never be used (see the data-leakage rule in section 8).

- [ ] Register at the contest site and provision the trial through the contest's sign-up link, not a generic Snowflake trial, so the sponsor credit applies.
- [ ] Choose AWS us-west-2 or us-east-1 at signup. This is the single most consequential setup choice; see A.4.
- [ ] Generate a PAT (A.3) with an explicit expiry. The default is 15 days and the contest runs into September.
- [ ] Create a network policy for the development IP up front. A PAT cannot be used without one, and the bypass parameter caps at 1440 minutes.
- [ ] Run `SHOW CORTEX BASE MODELS` to lock the exact GA Claude model id for the account region. Do not assume `claude-sonnet-4-5`; the availability table also lists newer variants and GA names move.

Operational constraint: trial accounts without a payment method are throttled to roughly ten credits per day of Cortex usage. That is the binding limit, not the 400 USD balance, which is ample (roughly 130-200 credits against an estimated 100-250 for the whole build). Ten credits per day is roughly one million output tokens - workable for iterative development, tight for an autonomous-agent burn-in. Adding a payment method lifts the cap while still consuming the free balance first, so it costs nothing to do preemptively. Warehouse compute draws on the same balance as inference.

### 7b. Remaining owner-action blocker

- [ ] CAVEAT 2 - "Built with CoCo" submission requirement. Confirm with the CTO or the hackathon brief exactly what proof the submission requires that the app was built with CoCo (Cortex Code). This is a tooling and workflow requirement largely independent of the app, and it may change how the build is done, so it is expensive to discover late. Install the CoCo CLI and capture the required evidence format. This is now the only item genuinely gated on someone else, and it should not hold up account provisioning or Phase 1.

### 7c. Standard prep

- [x] Synthetic dataset generator built and tested. Lives at `synthetic_data/` (untracked staging; moves into the fork at Phase 1). Generates about 230,000 shots across 8 machines and 5 behavioural archetypes plus the MOLD, COMPANY, LOCATION, PART and WORK_ORDER dimensions, matching the production MASTER_SHOT_TABLE contract column for column. Each generation emits a `ground_truth.json` declaring the expected finding per machine, so the agent's autonomous output is scored against a contract. See that directory's README for the planted defects and the design constraints.
- [ ] Confirm team registration status. Eligibility per the official terms is 18 or older (not 20) and legal residence in India, ASEAN, Australia, New Zealand, South Korea, Japan, Sri Lanka, Bangladesh or Nepal. Teams of 1-4, free to enter, 10,000 USD prize pool.
- [ ] Run the Day-1 Path B validation call (Appendix A.6) to resolve the unconfirmed Cortex Agents details before committing to Path B. Note that under the compressed timeline in section 2, the default is to skip Path B entirely.

## 8. Risk register and cut lines

- Cortex client-side custom-tool ergonomics differ from Bedrock return-control: validated in Phase 0 spike; if the flow is awkward, fall back to Path A own-the-loop for everything and drop Path B.
- Cut line if behind schedule: drop Cortex Agents (keep Path A loop with Cortex COMPLETE-style messages), drop Cortex Analyst (keep templated anomaly SQL). The autonomous controller is the non-negotiable core.
- Data leakage: hard rule - no real credentials or client schemas in the fork or its history. Verify before every push.
- Model gating: tool-calling works only on Claude and OpenAI families; never fall back to Llama or Mistral inside the loop.

## Appendix A - Cortex integration reference

Confidence markers: [verified] = confirmed against official docs; [unconfirmed] = single-source, must be validated against a live account before relying on it.

### A.1 Path A - Cortex REST `/messages` own-the-loop tool call [verified]

Endpoint (account identifier such as `orgname-accountname` becomes the host):

```
POST https://<account_identifier>.snowflakecomputing.com/api/v2/cortex/v1/messages
```

Required headers:
- `Authorization: Bearer <SNOWFLAKE_PAT>`
- `Content-Type: application/json`
- `anthropic-version: 2023-06-01`
- `X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN` (recommended)

This is the Anthropic Messages wire format. The only difference from calling Anthropic directly is that the credential is a Snowflake PAT in `Authorization: Bearer`, not `x-api-key`. Claude models only. The existing BedrockClient loop maps onto this almost verbatim; the four parser helpers keep their contracts.

```python
"""Cortex Messages API own-the-loop tool call using a Snowflake PAT as a bearer token.
Demonstrates the Anthropic-style tool_use / tool_result round trip against Cortex.
Pure REST via requests; no Snowflake SDK required."""

import json
import os
import requests

SNOWFLAKE_ACCOUNT = os.environ["SNOWFLAKE_ACCOUNT"]            # e.g. "myorg-myacct"
SNOWFLAKE_PAT = os.environ["SNOWFLAKE_PAT"]                    # token secret
CORTEX_MODEL = os.getenv("CORTEX_MODEL", "claude-sonnet-4-5")  # verify with SHOW CORTEX BASE MODELS
MAX_TOKENS = int(os.getenv("CORTEX_MAX_TOKENS", "1024"))

BASE_URL = f"https://{SNOWFLAKE_ACCOUNT}.snowflakecomputing.com/api/v2/cortex/v1/messages"
HEADERS = {
    "Authorization": f"Bearer {SNOWFLAKE_PAT}",
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
    "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
}

TOOLS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    }
]


def execute_tool(name: str, tool_input: dict) -> str:
    """Client-side tool implementation. Returns a JSON string result."""
    if name == "get_weather":
        return json.dumps({"temperature": "69F", "condition": "sunny"})
    return json.dumps({"error": f"unknown tool {name}"})


def post_messages(messages: list) -> dict:
    """Single POST to the Cortex Messages endpoint. Returns the parsed assistant message."""
    payload = {"model": CORTEX_MODEL, "max_tokens": MAX_TOKENS, "messages": messages, "tools": TOOLS}
    resp = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def run_conversation(user_text: str) -> str:
    """Own-the-loop: POST, execute any tool_use, append tool_result, re-POST until stop."""
    messages = [{"role": "user", "content": user_text}]
    while True:
        assistant = post_messages(messages)
        messages.append({"role": "assistant", "content": assistant["content"]})
        if assistant.get("stop_reason") != "tool_use":
            return "".join(b["text"] for b in assistant["content"] if b["type"] == "text")
        tool_results = []
        for block in assistant["content"]:
            if block["type"] == "tool_use":
                result = execute_tool(block["name"], block["input"])
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block["id"], "content": result}
                )
        messages.append({"role": "user", "content": tool_results})
```

Response when the model wants a tool has `stop_reason: "tool_use"` and a `tool_use` content block with `id`, `name`, `input`. You reply with a `user` message carrying `tool_result` blocks keyed by `tool_use_id`, then re-POST the full messages array.

OpenAI-style alternative `POST /api/v2/cortex/v1/chat/completions` exists (tools use `parameters`, response has `tool_calls` with `finish_reason: "tool_calls"`, results returned as `{"role": "tool", ...}`) and supports non-Claude models, but the Messages API is the more faithful path for a Claude build.

### A.2 Path B - Cortex Agents `agent:run` with client-side custom tools [unconfirmed]

Endpoints (same host and auth as A.1, plus `Accept: application/json` with `"stream": false`, or `Accept: text/event-stream` for streaming which is the default):

```
POST /api/v2/cortex/agent:run                                          # inline, no stored object
POST /api/v2/databases/{database}/schemas/{schema}/agents/{name}:run   # stored agent object
```

Client-side custom tool declaration (best-supported shape, validate before relying on it): a `generic` tool type whose `tool_resources` entry is `{"type": "function"}` with no server-side `identifier`/`execution_environment`/`semantic_model_file`/`search_service` binding. The absence of a server-side binding is what makes Snowflake hand the call back to the client.

```json
{
  "tools": [
    {"tool_spec": {"type": "generic", "name": "my_custom_tool",
      "description": "Custom client-side function.",
      "input_schema": {"type": "object",
        "properties": {"param1": {"type": "string"}}, "required": ["param1"]}}}
  ],
  "tool_resources": {"my_custom_tool": {"type": "function"}}
}
```

When the agent calls the tool, a `response.tool_use` event carries `tool_use_id`, `name`, `input`, and a `client_side_execute: true` signal. You continue the same `:run` endpoint referencing `thread_id` + `parent_message_id` (the id of the assistant message that emitted the call) with a `tool_result` content block. The exact result nesting is the least-confirmed detail and should be learned from a live 400 response.

Server-side tools contrast: Cortex Analyst binds `tool_resources` to a `semantic_model_file` (or semantic view), Cortex Search binds to a `search_service`. These run inside Snowflake and are how the interactive NL-query surface gets built.

SQL alternative for prototyping without HTTP: `SNOWFLAKE.CORTEX.DATA_AGENT_RUN('<db.schema.agent>', '<json_body>')`. Useful for server-side agents; not usable for a client-side tool loop (nothing to hand back to).

### A.3 PAT setup [verified]

```sql
ALTER USER IF EXISTS my_user ADD PROGRAMMATIC ACCESS TOKEN cortex_token
  DAYS_TO_EXPIRY = 90                   -- default is only 15; the contest runs into September
  ROLE_RESTRICTION = 'MY_CORTEX_ROLE'   -- role must hold SNOWFLAKE.CORTEX_USER
  COMMENT = 'hackathon cortex REST';
-- Secret is returned ONCE. Copy immediately; store as a secret, never in git.
```

Gotchas: `DAYS_TO_EXPIRY` default 15, range 1-365. Set it explicitly; a 15-day token expires mid-build. Maximum 15 tokens per user. The restricted role must hold the `SNOWFLAKE.CORTEX_USER` database role (or `SNOWFLAKE.CORTEX_REST_API_USER`), typically granted to PUBLIC already. Header value is exactly `Authorization: Bearer <token_secret>`.

Network policy: a PAT cannot be *used* without one. A human (`TYPE=PERSON`) user can generate a token without a policy but still needs one to authenticate with it; a `TYPE=SERVICE` user needs one to both generate and use. `MINS_TO_BYPASS_NETWORK_POLICY_REQUIREMENT = <n>` caps at 1440 minutes (one day), so it is a same-day unblock, not a solution for a multi-week build. Create a permissive policy for the development IP range up front instead. The parameter bypasses the requirement to *have* a policy, not the rules of one that already exists.

### A.4 Account region and model check [verified, corrected 2026-07-21]

Correction: an earlier draft of this section said to set `CORTEX_ENABLED_CROSS_REGION = 'AWS_APJ'` to match the account's region family. That advice was wrong and would have forced the build onto cross-region inference unnecessarily.

Claude Sonnet is not natively available in any AWS APJ region. Per the Cortex regional availability table, `claude-sonnet-4-5` is native only to AWS us-west-2 (Oregon), AWS us-east-1 (N. Virginia), and Azure East US 2. APJ regions natively serve Llama and Mistral families, which the risk register in section 8 forbids inside the tool loop because tool-calling is supported only on Claude and OpenAI families.

Therefore: provision the account in AWS us-west-2 or us-east-1 and the cross-region question disappears entirely. Nothing in the contest rules mandates an APJ region; the APJ requirement applies to the entrant's residence, not the account's region.

```sql
-- Ground truth for what this account can actually call (lifecycle stage + available_regions):
SHOW CORTEX BASE MODELS;

-- Only needed if the account was provisioned outside a Claude-native region (ACCOUNTADMIN only):
USE ROLE ACCOUNTADMIN;
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';
```

Cross-region inference, if it proves unavoidable, is account-level only, carries no data egress charge and no cost premium (credits bill in the requesting region), and keeps data at rest in the home region while inference payloads transit. Latency is provider-dependent and should be measured, not assumed.

Model id guidance: `claude-sonnet-4-5` is the safe default, but the availability table also lists newer variants (`claude-sonnet-4-6`, `claude-sonnet-55`) and GA names move, so re-check at build time. Treat marketing-blog GA and preview claims as unreliable; the ground truth for the account is `SHOW CORTEX BASE MODELS`. Avoid preview models for the demo.

Inference cost, per million tokens (Snowflake Service Consumption Table, effective 2026-07-14): `claude-sonnet-4-5` and `-4-6` bill 1.80 credits input and 9.00 output; `claude-sonnet-55` bills 1.20 and 6.00. With prompt caching on `claude-sonnet-4-5`: 1.50 input, 7.50 output, 1.875 cache write, 0.15 cache read.

### A.5 SDK vs raw REST [verified]

Use raw REST for both paths during the build. `snowflake.core` ships `CortexAgentService.run()` (wraps `agent:run`, returns an SSE client) but its request-model field docs are thin. Raw REST keeps the client-side tool round trip (the actual risk area) explicit and debuggable. The official `anthropic` Python SDK can be pointed at the Cortex base URL with a Bearer PAT if a typed Messages client is preferred later.

### A.6 Day-1 validation tasks (burn down Path B unknowns)

Before committing to Path B, one live call resolves every unconfirmed item. With the PAT created (A.3):

1. POST `/api/v2/cortex/agent:run` with `"stream": false` and a single one-field `generic` client-side tool; dump the raw response JSON to confirm the `tool_spec`/`tool_resources` discriminator and the tool-call event shape.
2. Reply with a `tool_result` and drive a deliberate 400 to learn the exact result nesting and the `thread_id`/`parent_message_id` contract.
3. Run `SHOW CORTEX BASE MODELS` to lock the exact GA Claude model id for the account region.

If Path B proves awkward in these three calls, fall back to Path A for the entire agent (own-the-loop with `/messages`) and keep Cortex Analyst as a standalone interactive surface rather than an in-agent tool. Path A alone still satisfies the track.
