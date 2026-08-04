# Autonomous Manufacturing Workflow Agent

An AI-driven system that senses production anomalies in injection-moulding equipment,
reasons across multiple signals using Snowflake Cortex (Claude), and autonomously
executes multi-step investigative workflows -- with no human in the loop.

Built for the Snowflake CoCo CLI Hackathon 2026 (Intelligent Workflow Automation Agent track).

## The Problem

Manufacturing lines generate millions of shots per week. Dashboards track single metrics
(cycle time, stop count) but subtle multi-signal anomalies slip through:

- A machine drifting 2% per week looks healthy on any single-day view
- High MTTR with normal MTBF means few faults but slow recovery -- invisible to stop-count alerts
- Declining week-over-week stability is the earliest warning, but no threshold catches a trend

**This agent reasons across detectors the way an experienced engineer does** -- combining
cycle time deviation and stability trends to surface what single-metric monitors miss.

## Demo Headline

Machine **MX-7103** drifts from 1.9% to 24.0% above approved cycle time over six weeks while
its stability score stays at 90% -- statistically indistinguishable from healthy machines.
A threshold-based monitor never fires. The agent catches it by reasoning across CT deviation
and stability signals, then autonomously runs root cause analysis and records the finding.

## Architecture

```
Trigger (schedule/manual)
    |
    v
[Sense] CT Deviation + Stability sweep across fleet
    |
    v
[Reason] Cortex LLM (Claude) cross-signal analysis
    |       - Which machines are truly abnormal?
    |       - What follow-up tools should run?
    v
[Act] RCA, Save Insights (tool dispatch)
    |
    v
[Record] Decision trail + self-grade against ground truth
```

Single FastAPI application. Cortex REST Messages API for LLM. All data in Snowflake
(`MMS_DEMO.PUBLIC.MASTER_SHOT_TABLE`). 243,000 synthetic shots across 8 machines, 6 weeks.

## CoCo CLI Skills (3)

| Skill | Purpose |
|---|---|
| `$sense-equipment-anomalies` | Sweep the fleet for production anomalies and rank what is abnormal |
| `$investigate-shift-notes` | Search operator notes to explain WHY a machine is drifting |
| `$report-and-act` | Record the decision and actions to an auditable trail, then grade it |

Each skill works standalone in a CoCo session or chains into the autonomous workflow.

## Quick Start

```bash
# Prerequisites
pip install -r requirements.txt

# 1. Generate and load synthetic data (one-time)
python -m synthetic_data.generate --database MMS_DEMO --schema PUBLIC --load

# 2. Run the autonomous agent (headless, end-to-end)
LOCAL_DATA_DIR=./synthetic_out python scripts/run_agent.py

# 3. Smoke-test the LLM connection
LOCAL_DATA_DIR=./synthetic_out python scripts/smoke_llm.py

# 4. Launch the demo UI
LOCAL_DATA_DIR=./synthetic_out streamlit run demo/app.py

# 5. Run the test suite (716 tests)
pytest tests/ synthetic_data/tests/ -v
```

Set `LOCAL_DATA_DIR=./synthetic_out` to run everything off local CSV (no Snowflake needed
for development). Remove it to query the live Snowflake account.

## Configuration

Copy `COPY_TO_ENV.txt` to `.env` and fill in:

```
SNOWFLAKE_ACCOUNT=your-account
SNOWFLAKE_USER=your-user
SNOWFLAKE_PASSWORD=your-password
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=MMS_DEMO
SNOWFLAKE_SCHEMA=PUBLIC
SNOWFLAKE_PAT=your-programmatic-access-token
LLM_BACKEND=cortex
```

## What Makes This Different

1. **Autonomous multi-step orchestration** -- the agent decides what tools to call next based
   on what it found, not a hardcoded DAG
2. **Cross-signal reasoning** -- combines 4 independent detectors (CT deviation, MTBF, MTTR,
   stability trend) that no single threshold can replicate
3. **Self-grading** -- every run is scored against a ground-truth contract declaring what
   defects are planted, so claims are verifiable
4. **Minimal intervention** -- one trigger, zero human decisions, full decision trail

## Project Structure

```
scripts/run_agent.py          Entry point: one autonomous sense-reason-act cycle
skills/                       3 CoCo CLI skills (sense, investigate, report)
demo/                         Streamlit UI (trigger runs, browse trails, visualize drift)
analysis/                     Analysis modules (ct_deviation, rca, roi, ct_efficiency, ...)
services/workflow/            Autonomous controller, scoring, decision trail
core/                         LLM clients (Cortex + MLX), tool definitions, prompts
synthetic_data/               Reproducible dataset generator with planted defects
tests/                        716 tests (684 application + 40 generator)
```

## Judging Criteria Mapping

| Criterion | How this project addresses it |
|---|---|
| Real-world relevance | Injection moulding CT drift detection -- a real operations problem |
| Multi-step orchestration | Sense -> Reason -> Act loop with dynamic tool selection |
| Error handling | Failed detectors don't halt; missing signal is reported, not hidden |
| CoCo CLI usage | 3 modular skills, Cortex LLM API, Snowflake data |
| End-to-end completeness | Data generation -> anomaly detection -> RCA -> decision trail -> grading |
| Minimal intervention | Fully headless; triggered by schedule or single command |
