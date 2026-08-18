---
name: report-and-act
description: >
  Record a manufacturing decision and the actions taken to a durable, auditable decision
  trail, then review or grade it. Persists the equipment flagged, the severity assigned, the
  evidence relied on, and every action actually performed, so a run can be audited after the
  fact rather than taken on trust.
  Triggers: log this decision, record the finding, write it to the trail, what did the agent
  do, show the decision trail, audit the run, score the run, was that correct, close out the
  investigation, document the action taken.
  Use when: you have finished investigating and reached a conclusion, or you need to review
  or verify a previous run.
  Not for: deciding what is wrong - use sense-equipment-anomalies and investigate-shift-notes.
---

# Report and Act

Closes a workflow by writing down what you concluded, what you relied on, and what you did.
The trail is the record; your summary is a claim. This skill keeps the two separate on
purpose.

## When to Use

- You have finished sensing and investigating and have a conclusion to commit
- You need to show what a previous run actually did, not what it said it did
- You want to grade a run against the dataset's known defects

## Workflow

### Step 1: Record the decision

```bash
python skills/report-and-act/scripts/record_decision.py \
  --equipment MX-7103 --severity high \
  --finding "Duration drifting, 12.6 percent above approved and still rising" \
  --evidence "risk tower: no stop-based signal, mttr_vs_peers 0.43" \
  --evidence "shift note 2026-06-15: parts releasing slower from the cavity" \
  --action "generated duration deviation report"
```

Pass `--equipment` once per machine and `--evidence` once per supporting fact.

**Only pass `--action` for work you actually performed.** If you assessed a machine but took
no action, omit the flag entirely. The script will note that the run is an assessment rather
than an intervention, which is accurate and expected.

### Step 2: Review what was recorded

```bash
python skills/report-and-act/scripts/show_trail.py            # most recent run
python skills/report-and-act/scripts/show_trail.py <run_id>   # a specific run
```

With `LOCAL_DATA_DIR` set, this also grades the run against the dataset's planted defects and
prints precision, recall and f1.

### Step 3: Read the score honestly

- **`missed`** are real defects you did not flag. That is the cost of a narrow sweep.
- **`false +`** are healthy machines you flagged. Each one sends an engineer to a working
  line, so precision matters as much as recall.
- **`UNBACKED CLAIMS`** are machines your summary named but that appear in no recorded action.
  If this list is non-empty, the summary describes work the trail has no record of. Correct
  the summary rather than the trail.

## Common Mistakes

- **Recording intended actions as performed.** "Scheduled an inspection" belongs in
  `--action` only if you scheduled one. Language models routinely narrate tool calls they
  never made; this trail exists specifically to catch that, and it will.
- **Evidence without attribution.** "Notes mention drift" is not evidence. "Shift note
  2026-06-15: parts releasing slower" is. Quote the date and the text.
- **Recording a decision you did not reach.** If the sweep was inconclusive, say so and
  assign a low severity, rather than manufacturing a finding to close the loop.
- **Treating a good score as proof.** The score grades against a synthetic contract with
  known defects. It measures whether the workflow works, not whether the plant is healthy.
