# Cortex Workflow Agent

An autonomous manufacturing workflow agent, built for the Snowflake CoCo (Cortex Code) CLI
Hackathon 2026.

Most manufacturing analytics answers a question a human already thought to ask. This agent runs
on a trigger instead of a prompt: it senses anomalies in shot-level production data, reasons over
them with an LLM, decides what matters, and chains the follow-up actions itself, leaving a
decision trail behind.

**All data in this repository is synthetic.** It is generated, not collected, and carries no real
company, plant, supplier or equipment.

## The problem it is built to demonstrate

A tool called `EMA-4103` drifts. Over six weeks its cycle time creeps from 1.9% to 24.0% above the
approved cycle time, crossing the warning threshold in week three and critical in week six.

Its stability sits at 90% the whole time, indistinguishable from the healthy machines around it.
Every stop-based metric says the machine is fine, because in stop terms it is: it never jams, it
just quietly makes everything slower. Watch one metric and the drift is invisible. Catching it
means holding cycle-time deviation and run-rate behaviour side by side and noticing they
disagree.

That is the case for an agent rather than a dashboard, and it is why the demo dataset is built
around a defect a single threshold cannot see.

## Quick start

```bash
pip install -r requirements.txt
cp COPY_TO_ENV.txt .env          # fill in Snowflake credentials

# Generate the dataset (CSV only; no Snowflake needed)
python -m synthetic_data.generate --output-dir ./synthetic_out

# Load it into a Snowflake account
python -m synthetic_data.generate --database MMS_DEMO --schema PUBLIC --load

# Run the server
python main.py

# Run the demo UI (offline, against the generated CSVs)
LOCAL_DATA_DIR=./synthetic_out ./start_demo.sh
```

The demo is at http://localhost:8501. It triggers a real headless agent run, shows the decision
trail it produced, and grades that run against the planted defects.

Then: Swagger at http://localhost:3020/docs, health at `/health`, MCP info at `/mcp/mcp/info`
(the doubled segment is real - `mcp_router` declares its own `/mcp/*` paths and is mounted under
the `/mcp` prefix).

```bash
pytest tests/ -v                  # application suite
pytest synthetic_data/tests/ -v   # generator suite (pure, no I/O)
```

## How it works

```
trigger (schedule or event)
     |
   sense     analysis modules over MASTER_SHOT_TABLE:
     |        cycle-time deviation, run rate, root cause,
     |        CT efficiency, capacity, tooling end-of-life
     |
   reason    LLM evaluates severity and likely cause across findings
     |
    act      chains actions: deeper analysis, report generation,
     |        email notification, scheduling a follow-up
     |
    log      every decision and action recorded for inspection
```

A single FastAPI application on port 3020 hosts all of it. Eight routers over seven prefixes:
`/analytics`, `/chat`, `/config`, `/email`, `/mcp`, `/monitoring` and `/scheduler` (the WebSocket
chat router shares the `/chat` prefix). Tools are dispatched by name through a registry, so the
same implementations serve the chat surface, the MCP contract and the autonomous loop.

The LLM client is pluggable behind a backend factory (`core/llm_backend.py`, selected by
`LLM_BACKEND`): the Snowflake Cortex Messages API is the default and the submission path, with a
local MLX client as an Apple-Silicon development stand-in that returns responses in the same
Anthropic shape, so the loop and parsers never branch on backend.

## The data

One denormalised fact table, `MASTER_SHOT_TABLE`, holding one row per injection-moulding shot:
cycle time, approved cycle time, timestamp, equipment, supplier, part, tooling. Every analysis
reads from it directly. There is no precomputed summary table; at demo scale it earns nothing and
costs a synchronisation problem.

`synthetic_data/` generates roughly 230,000 shots across 8 machines and 5 behavioural archetypes
over 6 weeks, plus the mold, company, location, part and work-order dimensions. Generation is pure
and seeded, so a given seed reproduces the dataset byte for byte.

Every defect is planted deliberately and written to a `ground_truth.json` beside the data,
declaring the finding each machine should produce, which detector should produce it, and the
margin it should clear. Four machines are negative controls that must not be flagged. The agent's
output is therefore checkable against a contract rather than against a recollection of what was
seeded.

See `synthetic_data/README.md` for the planted defects and the non-obvious design constraints.

## Status

Working: the analytics surface, the tool-calling loop, the tool dispatch registry, the scheduler
and job queue, and the synthetic dataset with its verification contract. 724 tests pass (684
application, 40 generator).

Built: the LLM client is ported off AWS Bedrock to the Snowflake Cortex REST Messages API
(`core/cortex_client.py` plus the pure `cortex_wire`/`cortex_adapter` helpers), behind a backend
factory that also offers a local MLX stand-in for offline development. The autonomous controller
(`services/workflow/`) runs the headless sense-reason-act loop and writes a decision trail
(`models/decision_trail.py`); `scripts/run_agent.py` drives one run and self-grades it. Three
agent skills, a shift-notes search surface, the Risk Tower detector, and an offline data seam
(`LOCAL_DATA_DIR` serving the generator CSVs without Snowflake) are in place. The Streamlit demo
(`demo/`) triggers a run, renders its decision trail grouped into sense, reason and act, grades it
against ground truth, and charts the six-week drift the agent has to catch.

Outstanding: the Cortex Analyst interactive surface, and the submission writeup and video. First
contact against a live hackathon Snowflake account (PAT auth, PUT/COPY load, the exact GA Claude
model id) is still untested; the code is written but has only run against synthetic CSVs and the
MLX backend, so no demo run has yet reasoned on Cortex.

`HACKATHON_PLAN.md` holds the build plan and the verified Cortex integration reference.
`CLAUDE.md` holds the architecture and conventions, including several traps worth reading before
deleting anything.
