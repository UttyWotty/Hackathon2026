---
name: investigate-shift-notes
description: >
  Search operator and maintenance shift notes to explain WHY a machine is behaving abnormally,
  and to establish how long the problem has been visible to the people on the floor. Retrieves
  free-text notes from the SHIFT_NOTE table, by equipment and by meaning.
  Triggers: why is this machine drifting, what did the operators say, shift notes, maintenance
  log, has anyone noticed, when did this start, operator comments, has this been reported,
  what is the history on, corroborate the anomaly, root cause context.
  Use when: a numeric detector has already flagged a machine and you need the human account
  of it, or you need to know when a problem was first observed.
  Not for: finding which machines are abnormal - use sense-equipment-anomalies first.
---

# Investigate Shift Notes

Numeric detectors report that something changed. Shift notes usually say what it looked like
and when someone first noticed. Use this to turn a metric into an explanation.

## When to Use

- A machine has been flagged and you need a probable cause, not just a measurement
- You need to establish how long a problem has been visible to operators
- You want to check whether an anomaly was already known before escalating it

## Prerequisites

Either a Cortex Search service over `SHIFT_NOTE`, or `LOCAL_DATA_DIR` for offline work. The
script reports which engine served the results; do not conflate them.

Creating the service:

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE shift_note_search
  ON note_text
  ATTRIBUTES machine_id, shift_date
  WAREHOUSE = <warehouse>
  TARGET_LAG = '1 day'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  AS (SELECT note_text, machine_id, shift_date FROM SHIFT_NOTE);
```

## Workflow

### Step 1: Retrieve the notes

```bash
python skills/investigate-shift-notes/scripts/search_notes.py MX-7103
python skills/investigate-shift-notes/scripts/search_notes.py MX-7103 "cycle slower cooling"
```

Omit the query to get the machine's history in date order. Supply one to rank by relevance.

### Step 2: Establish the timeline, not just the content

The most valuable output is usually *when* the first relevant note appears, compared with when
the metric crossed its threshold. A note describing a symptom weeks before the numbers moved is
the strongest evidence you can bring: it shows the problem was observable and unactioned.

State both dates explicitly.

### Step 3: Read the notes as evidence, with their limits

- Notes are written by shift, so gaps mean nobody wrote anything, not that nothing happened.
- Language escalates as a problem worsens. Compare early and late wording rather than reading
  the latest note alone.
- A routine note on a bad day is normal. Absence of complaint is weak evidence.

### Step 4: Attribute your conclusion

Quote the note text and date you relied on. A cause inferred from notes must be traceable to
the note that supports it.

## Common Mistakes

- **Presenting lexical results as semantic.** Without the Cortex Search service the script
  matches shared words only. It will miss a paraphrase. Say which mode produced the answer.
- **Concluding "no problem" from no results.** An empty result means nothing was written that
  matched, which is not the same as nothing happening.
- **Searching before sensing.** Notes explain a flagged anomaly. They are a poor way to find
  one, because every machine has notes.
- **Quoting a note without its date.** The timeline is the point.
