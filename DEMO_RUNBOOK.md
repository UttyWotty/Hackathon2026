# Demo Runbook - Autonomous Manufacturing Workflow Agent

This document covers the live demo flow for the consulting session.
It includes pre-demo setup, the recommended walkthrough sequence, and
fallback notes for known platform constraints.

## Access

- **Snowsight URL:** `https://app.snowflake.com/IQSISUH/rb95130/`
- **Demo user:** `DEMO_USER` (role: `DEMO_ROLE`, warehouse: `COMPUTE_WH`)
- **App:** Streamlit Apps > `AUTONOMOUS_MFG_AGENT_DEMO`

## Pre-Demo State Reset

Run these as ACCOUNTADMIN before the session:

```sql
TRUNCATE TABLE DEMO.PUBLIC.AUDIT_LOG;
DELETE FROM DEMO.PUBLIC.SHOT_DATA WHERE MACHINE_ID = 'MX-9201';
UPDATE DEMO.PUBLIC.SHOT_DATA SET STATUS = 'active' WHERE STATUS != 'active';
```

This gives: 8 machines, all active, empty audit trail, no MX-9201.

## Demo Flow (Recommended Sequence)

### 1. Fleet Sweep (Sense)

- Click **"Run Fleet Sweep"** in the sidebar
- MX-7103 appears as WARNING (12.6% deviation, 92.7% stability)
- **Autonomous actions fire** for MX-7103 (exceeds 10% threshold)
- Work order + alert + status change happen without clicking anything
- Show the **Agent Activity Log** (expanded by default) -- real-time skill invocations
- Show the **Audit Trail** -- persistent Snowflake records with webhook payload

### 2. Investigation (Reason)

- In sidebar under "Investigate Equipment", select **MX-7103**
- Click **"Run Investigation"**
- Two panels appear: weekly duration trend + operator shift notes
- Point out: the agent cross-references quantitative drift with unstructured text
- Click **"Mark MX-7103 resolved"** to complete the loop
- Activity log shows: `$investigate-shift-notes -- Investigation complete`

### 3. Ingest New Telemetry (Act on fresh data)

- Click **"Open CSV Paste Dialog"** in sidebar
- Click **"Load MX-9201 (3K rows)"** to load the sample
- Click **"Ingest to Snowflake"**
- Auto-sweep fires with new data included
- MX-9201 appears as CRITICAL (15.0% deviation, 85.4% stability)
- Autonomous actions fire for MX-9201 only (MX-7103 already resolved)
- KPIs update: 9 machines, worst deviation 15.0%

### 4. Corroboration Evidence (Drift Detection tab)

- Scroll to "Corroborating Evidence: Telemetry + Operator Notes"
- Highlighted notes show explicit timestamp linkage:
  > "Corroborates 15.4% deviation spike (week of 2026-07-06)"
- This is the exact item the feedback requested

### 5. Webhook Payload (Audit Trail)

- In the Audit Trail section, the latest webhook dispatch renders as a formatted card
- Same Cards v2 schema as the backend Google Chat client
- Talking point: "SiS sandbox can't make outbound HTTP (trial account, no EAI),
  but the payload is production-ready -- identical to what lands in Google Chat"

## Key Talking Points

| Feedback Item | How We Address It |
|---|---|
| Real webhook delivery | Cards v2 payload stored + rendered; backend client POSTs same schema |
| Autonomous action | Agent acts at 10% threshold without human click |
| Equipment status update | STATUS_CHANGE written automatically on sweep |
| CSV upload | Paste + ingest with auto-sweep; 3K-row demo file included |
| Visible skill invocations | Activity log default-open, tied to real invocations |
| Corroboration linkage | Each note labeled with the specific spike it explains |

## Platform Constraints (Honest Answers)

- **No outbound HTTP from SiS:** Trial account blocks External Access Integration.
  The webhook payload is constructed and stored; external delivery is via backend.
- **st.file_uploader unavailable:** SiS runs Streamlit 1.22; file_uploader requires 1.26+.
  Paste approach works identically for the data path.
- **Session state resets on page reload:** `actioned_machines` and `resolved_machines`
  live in browser session. Fresh page load = agent will re-detect and re-action.
  The audit trail (Snowflake table) provides the persistent record.

## Files Modified in This Session

- `src/frontend/action_loop.py` -- webhook payload, autonomous dedup, severity fix
- `src/frontend/streamlit_app.py` -- corroboration linkage, KPI cards, auto-sweep
- `src/frontend/interactive_controls.py` -- CSV paste, resolve button, MX-9201 loader
- `src/frontend/sample_telemetry_MX9201.csv` -- 3000-row sample (6 weeks, high drift + low stability)
- `src/frontend/snowflake.yml` -- added CSV artifact
- `copy_to_env.txt` -- env template for SME (no credentials)
- `demo_runbook.md` -- this file
