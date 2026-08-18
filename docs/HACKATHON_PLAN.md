# Snowflake CoCo CLI Hackathon 2026 - Build Plan

This document tracks the build plan for the Snowflake CoCo (Cortex Code) CLI Hackathon 2026. The project is an Intelligent Workflow Automation Agent for manufacturing fleet anomaly detection.

## 1. Locked Decisions

- Track: Intelligent Workflow Automation Agent (sense anomalies, reason over them, autonomously trigger multi-step workflows).
- LLM: Snowflake Cortex (Claude Sonnet) via REST Messages API.
- Data: Synthetic manufacturing dataset (243K shots, 8 machines, 6 weeks) in Snowflake.
- Frontend: Streamlit-in-Snowflake interactive dashboard.
- Backend: FastAPI server with autonomous agent loop.

## 2. Timeline

- Registration: Jun 15 2026
- Refinement Phase: Aug 17-23 2026
- Submission Deadline: Aug 23, 11:59 PM IST
- SME Feedback Session: Aug 19, 15:00 IST

## 3. Architecture

A headless controller runs on trigger (schedule or manual command):

1. **Sense**: Run anomaly-detection sweep across the fleet ($sense-equipment-anomalies)
2. **Reason**: Cortex LLM evaluates severity and root cause across findings
3. **Act**: Agent chains actions - RCA, work orders, alerts ($report-and-act)
4. **Record**: Every decision logged to AUDIT_LOG for the demo

Interactive surface: Streamlit dashboard with on-demand controls.

## 4. Build Phases

- [x] Phase 0 - De-risk: Cortex tool-calling validated, feasible, no blockers
- [x] Phase 1 - Synthetic data generator + schema (243K shots, 8 machines, planted anomalies)
- [x] Phase 2 - Cortex Messages API port (own-the-loop, PAT auth)
- [x] Phase 3 - Autonomous controller + decision trail + 3 CoCo skills
- [x] Phase 4 - Interactive Streamlit dashboard deployed to Snowflake
- [x] Phase 5 - Refinement (evaluator feedback items 1-5):
  - [x] Demo credentials (DEMO_USER on competition account)
  - [x] Interactive dashboard (sweep, CSV upload, per-equipment RCA)
  - [x] Visible CoCo skill invocations (Agent Activity Log)
  - [x] Autonomous action loop (work orders + alerts -> AUDIT_LOG)
  - [x] Inline shift notes alongside telemetry drift graphs
- [x] Phase 6 - Schema rename (generic column/table names)
- [x] Phase 7 - Repo restructure (src/backend, src/frontend, docs, tests)
- [ ] Phase 8 - Final submission video and writeup (deadline: Aug 23)

## 5. Account Details

- Competition account: IQSISUH-RB95130
- Database: DEMO
- Schema: PUBLIC
- Tables: SHOT_DATA, TOOL, VENDOR, PRODUCT, LOCATION, SHIFT_NOTE, WORK_ORDER, AUDIT_LOG
- Streamlit: DEMO.PUBLIC.AUTONOMOUS_MFG_AGENT_DEMO
- Demo user: DEMO_USER (DEMO_ROLE with read + write access)

## 6. CoCo Skills

| Skill | Purpose |
|-------|---------|
| $sense-equipment-anomalies | Fleet-wide anomaly sweep: deviation + stability |
| $investigate-shift-notes | Semantic search over operator notes for root cause |
| $report-and-act | Log decisions, work orders, alerts to audit trail |

## 7. Key Insight Demonstrated

MX-7103 drifts from 2% to 24% above target duration over 6 weeks while stability stays at 90%. No single-metric threshold alert fires. The agent catches it by reasoning across deviation AND stability together - the "invisible anomaly" pattern that traditional monitors miss.

## 8. Risk Register

- [x] Cortex tool-calling works: validated
- [x] Data leakage: no real credentials in repo (synthetic data only)
- [x] Account expiry: migrated to competition credit account (valid through Aug 20)
- [ ] Video recording and writeup: must complete before Aug 23
