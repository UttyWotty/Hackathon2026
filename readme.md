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
```

Then: Swagger at http://localhost:3020/docs, health at `/health`, tool contract at `/mcp/info`.

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

A single FastAPI application on port 3020 hosts all of it. Eight routers, mounted at `/analytics`,
`/chat`, `/config`, `/database`, `/email`, `/mcp`, `/monitoring` and `/scheduler`. Tools are
dispatched by name through a registry, so the same implementations serve the chat surface, the
MCP contract and the autonomous loop.

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
and job queue, and the synthetic dataset with its verification contract. 500 tests pass.

Outstanding: the LLM client currently targets AWS Bedrock and is being ported to the Snowflake
Cortex REST Messages API, which is the same wire format and touches three call sites. The
autonomous controller and the decision log build on top of that.

`HACKATHON_PLAN.md` holds the build plan and the verified Cortex integration reference.
`CLAUDE.md` holds the architecture and conventions, including several traps worth reading before
deleting anything.
