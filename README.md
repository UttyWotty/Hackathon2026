# Autonomous Manufacturing Workflow Agent

An AI-driven system that senses production anomalies in injection-moulding equipment,
reasons across multiple signals using Snowflake Cortex (Claude Sonnet 4.5), and autonomously
executes multi-step investigative workflows -- with no human in the loop.

Built for the Snowflake CoCo CLI Hackathon 2026 (Intelligent Workflow Automation Agent track).

## The Problem

Manufacturing lines generate millions of shots per week. Dashboards track single metrics
(duration, stop count) but subtle multi-signal anomalies slip through:

- A machine drifting 2% per week looks healthy on any single-day view
- High stability with rising deviation is invisible to threshold alerts
- Declining week-over-week throughput is the earliest warning, but no single metric catches a trend

**This agent reasons across detectors the way an experienced engineer does** -- combining
duration deviation, stability trends, and maintenance history to surface what single-metric
monitors miss.

## Demo Headline

Machine **MX-7103** drifts from 2% to 24% above approved duration over six weeks while
its stability score stays at 90%. A threshold-based monitor never fires. The agent catches
it by reasoning across duration deviation and stability signals, then autonomously runs
root cause analysis, confirms post-maintenance degradation, and records the finding --
all in a single 90-second headless run.

## Architecture

```
Trigger (schedule / manual / CoCo skill)
    |
    v
[SENSE] Duration Deviation + Stability sweep across fleet
    |
    v
[REASON] Cortex LLM (Claude Sonnet 4.5) cross-signal analysis
    |       - Which machines are truly abnormal?
    |       - What follow-up tools should run?
    v
[ACT] Tool dispatch: SQL queries, mold history, maintenance impact,
    |  target validation, period comparison, save insights
    v
[RECORD] Decision trail persisted + exported to Snowflake
```

Single FastAPI backend. Cortex REST Messages API for LLM reasoning. Streamlit-in-Snowflake
frontend. All data in Snowflake (`DEMO.PUBLIC`). 243,000 synthetic shots across 8 machines,
6 weeks.

## CoCo CLI Skills (3)

| Skill | Purpose |
|---|---|
| `$sense-equipment-anomalies` | Sweep the fleet for production anomalies and rank what is abnormal |
| `$investigate-shift-notes` | Search operator notes to explain WHY a machine is drifting |
| `$report-and-act` | Record the decision and actions to an auditable trail |

Each skill works standalone in a CoCo session or chains into the autonomous workflow.

## Quick Start

```bash
# Prerequisites
pip install -r requirements.txt

# Configure (copy and fill in credentials)
cp .env.example src/backend/.env

# 1. Run the autonomous agent (headless, end-to-end)
cd src/backend
python scripts/run_agent.py

# 2. Export the decision trail to Snowflake (for the dashboard)
python scripts/export_trail.py

# 3. Launch the backend API
python main.py

# 4. Deploy the Streamlit dashboard to Snowflake
cd src/frontend
snow streamlit deploy --replace
```

## Configuration

Set in `src/backend/.env`:

```
SNOWFLAKE_ACCOUNT=your-org-your-account
SNOWFLAKE_USER=your-user
SNOWFLAKE_PASSWORD=your-password
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=DEMO
SNOWFLAKE_SCHEMA=PUBLIC
SNOWFLAKE_PAT=your-programmatic-access-token
```

## What Makes This Different

1. **Autonomous multi-step orchestration** -- the agent decides what tools to call next based
   on what it found, not a hardcoded DAG. 13-26 tool calls per run, self-directed.
2. **Cross-signal reasoning** -- combines duration deviation, stability scoring, maintenance
   impact analysis, and tooling EOL into a unified assessment no single threshold can replicate.
3. **Self-correcting** -- when SQL fails on unknown columns, the agent introspects the schema
   and retries with correct identifiers. Observable in the decision trail.
4. **Full decision trail** -- every step (sense, reason, act) is persisted with tool name,
   arguments, result, and duration. Exported to Snowflake for dashboard display.
5. **Minimal intervention** -- one trigger, zero human decisions, full audit trail.

## Project Structure

```
src/backend/
  scripts/run_agent.py        Entry point: one autonomous sense-reason-act cycle
  scripts/export_trail.py     Push decision trail from SQLite to Snowflake
  services/workflow/          Autonomous controller, scoring, decision trail
  core/                       Cortex client, tool definitions, prompts
  analysis/                   Analysis modules (deviation, rca, roi, efficiency)
  synthetic_data/             Reproducible dataset generator with planted defects

src/frontend/
  streamlit_app.py            Dashboard (deployed to Streamlit-in-Snowflake)
  help_chat.py                AI help agent (Cortex Complete)
  analysis_panels.py          LLM-driven 5 Whys, Pareto, efficiency panels

skills/                       3 CoCo CLI skills (sense, investigate, report)
tests/                        Unit tests
```

## Judging Criteria Mapping

| Criterion | How this project addresses it |
|---|---|
| Real-world relevance | Injection moulding duration drift detection -- a real operations problem |
| Multi-step orchestration | Sense -> Reason -> Act loop with dynamic tool selection (13-26 steps) |
| Error handling | Failed tools don't halt; agent introspects schema and recovers |
| CoCo CLI usage | 3 modular skills, Cortex LLM API, Snowflake data, Streamlit-in-Snowflake |
| End-to-end completeness | Data generation -> anomaly detection -> investigation -> decision trail |
| Minimal intervention | Fully headless; triggered by schedule or single command |
