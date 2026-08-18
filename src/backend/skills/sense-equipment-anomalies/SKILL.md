---
name: sense-equipment-anomalies
description: >
  Sweep injection-moulding equipment for production anomalies and rank what is abnormal.
  Detects duration drift against approved duration and declining week-over-week stability,
  reading shot-level data from SHOT_DATA.
  Triggers: which machines are underperforming, check the fleet for anomalies, is anything
  drifting, equipment health check, what looks abnormal, run the anomaly sweep, duration
  deviation, stability decline.
  Use when: starting an investigation and you do not yet know which equipment is at fault.
  Not for: explaining WHY a machine is degrading - use investigate-shift-notes for that.
---

# Sense Equipment Anomalies

Gathers the numeric signal for a manufacturing fleet and returns condensed findings. This
skill only observes. Judging severity and deciding what to do are your job, not the script's.

## When to Use

- The user asks which machines are unhealthy, drifting, or worth investigating
- You are beginning a workflow and need to establish what is actually wrong
- A follow-up check is needed after a repair or a process change

## Prerequisites

Either a Snowflake connection with `SHOT_DATA`, or `LOCAL_DATA_DIR` pointing at a
generated dataset for offline work. The script reads whichever is configured.

## Workflow

### Step 1: Run the sweep

```bash
python skills/sense-equipment-anomalies/scripts/sweep.py
```

Pass an equipment code as the first argument to narrow it to one machine.

The script runs process-duration deviation across the fleet.

### Step 2: Read across metrics

A machine is not abnormal because one number is high. Compare:

- **`deviation_percentage`** rising while stability stays high means process drift, typically
  tooling or cooling.
- **`stability_score`** declining week over week even if today's absolute
  numbers still look acceptable. This is the earliest warning available.

### Step 3: State what you concluded and why

Name the machines you consider abnormal, the metric that convinced you, and the machines you
deliberately cleared. A healthy machine flagged is a real cost: it sends an engineer to a
working line.

## Common Mistakes

- **Flagging on a single metric.** A machine can be drifting badly on duration while
  stability says it is fine. That combination is the interesting case, not a
  contradiction to resolve.
- **Treating a failed detector as an all-clear.** The script prints a warning when a detector
  fails. Missing signal is not absence of a problem; say so explicitly.
- **Reporting the whole table back.** Return your judgement, not the raw sweep.
- **Inventing follow-up analyses.** If you did not run a tool, do not report its results.
