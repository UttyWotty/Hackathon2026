# RunRate Analysis - Calculation Specifications

**Version:** 2.6
**Last Updated:** 2026-02-03
**Detail:** Added first shot handling logic, Risk Tower integration

This document defines the exact calculations used in the RunRate analysis.

---

## 🔑 Core Concepts

### Run Interval Threshold
- **Default:** 8 hours (28,800 seconds)
- **Purpose:** Separates distinct production runs
- **Impact:** Any gap > 8 hours creates a new run and is **excluded** from all calculations
- **Key Concept:** The app does not see time as continuous. It sees distinct "Production Runs."

### Mode Cycle Time (MODE_CT)
- **Calculation:** Statistical mode of ACTUAL_CT values (excluding CT=999.9)
- **Tolerance Band:** ±5% (configurable via `MODE_CT_TOLERANCE`)
- **Usage:** Baseline for stop detection and efficiency calculations

### Downtime Gap Tolerance
- **Default:** 2.0 seconds
- **Purpose:** Minimum idle time added to a cycle to classify it as a stop
- **Logic:** If `time_diff_sec > (previous_CT + 2.0)`, it is a Time Gap stop

---

## 📊 Time Component Calculations

### 1. Total Run Duration (TOTAL_RUN_TIME)

**Definition:** The sum of durations of all identified production runs, explicitly excluding idle gaps (nights/weekends) between runs.

**Formula:**
```
TOTAL_RUN_TIME (min) = [Σ SHOT_DIFF_SEC (excluding first shot)] + MODE_CT
                       ─────────────────────────────────────────────────────
                                            60
```

**Implementation:**
- Sum all `SHOT_DIFF_SEC` values within a run
- Exclude the first shot's `SHOT_DIFF_SEC` (represents break before run)
- Add the mode cycle time for the last shot
- Convert seconds to minutes

---

### 2. Production Time (PRODUCTION_TIME)

**Definition:** Time spent actively producing parts at normal cycle times.

**Formula:**
```
PRODUCTION_TIME (min) = Σ SHOT_DIFF_SEC (for STOP=0 shots, excluding first)
                        ──────────────────────────────────────────────────
                                              60
```

**Special Cases:**
- If `ACTUAL_CT = 999.9` (hard stop code), use `SHOT_DIFF_SEC` instead
- Only count shots where `STOP = 0` (normal production)
- Exclude first shot's interval

---

### 3. Downtime Duration (TOTAL_DOWN_TIME)

**Definition:** Time lost due to stops, delays, and abnormal cycles.

**Formula (V2.6):**
```
TOTAL_DOWN_TIME (min) = Σ ADJ_CT_SEC (for STOP=1 shots)
                        ─────────────────────────────────
                                      60
```

**ADJ_CT_SEC (Adjusted Downtime) per shot type:**
| Stop Type       | ADJ_CT_SEC Value                |
|-----------------|--------------------------------|
| Normal          | 0                              |
| Hard Stop       | time_diff_sec (the gap)        |
| Abnormal Cycle  | ACTUAL_CT (the slow/fast cycle)|
| Time Gap        | time_diff_sec (the gap)        |

---

## 🛠️ Stop Detection Logic (V2.6)

A shot is flagged as a STOP (`STOP = 1`) based on these conditions, **checked in order**:

### Rule 1: First Shot of Run
```
First shot → ALWAYS stop_flag = 0 (Normal Production)
```
**Rationale:** The first shot of any new run is always classified as Normal Production. Since there is no previous shot within the run to calculate a gap against, it cannot be a "Stop."

### Rule 2: Hard Stop Code
```
Current ACTUAL_CT >= 999.9 → STOP
```
System-defined hard stop indicator.

### Rule 3: Abnormal Cycle Time
```
Current ACTUAL_CT < (MODE_CT × 0.95) → STOP (Fast Cycle)
Current ACTUAL_CT > (MODE_CT × 1.05) → STOP (Slow Cycle)
```
Cycle time is outside the ±5% tolerance band.

### Rule 4: Time Gap Detection
```
time_diff_sec > (previous ACTUAL_CT + 2.0 seconds) → STOP (Time Gap)
```
Significant delay between shots (micro-stop or delay).

### Exclusions:
- First shot in a run (Rule 1)
- Gaps > 8 hours (create new runs, first shot of new run is Normal)

**Code Location:** `session_analyzer.py` `_detect_stops_v26()` function

---

## 📈 KPI Calculations

### Efficiency (%)

**Definition:** Percentage of shots produced at normal cycle times.

**Formula:**
```
EFFICIENCY (%) = (Normal Shots / Total Shots) × 100

Where:
  Normal Shots = count of STOP = 0
  Total Shots = total number of shots in session
```

---

### Stability Index (UPTIME_PCT)

**Definition:** An uptime metric. Measures the % of active run time spent actually producing at cycle times within the mode CT tolerance.

**Formula:**
```
STABILITY INDEX (%) = (PRODUCTION_TIME / TOTAL_RUN_TIME) × 100
```

**Note:** This is the primary metric for Risk Tower analysis.

---

### Stop Events vs Individual Stops

**Stop Events (TOTAL_STOPS):**
- Count of **distinct** stop incidents
- Consecutive stopped shots = 1 event
- Example: 5 stopped shots in a row = 1 stop event

**Individual Stops (INDIVIDUAL_STOPS):**
- Count of **individual** stopped shots
- Example: 5 stopped shots in a row = 5 individual stops

---

## 🔧 Maintenance Metrics

### MTTR (Mean Time To Repair)

**Definition:** Average duration of a single stop.

**Formula:**
```
MTTR (min) = TOTAL_DOWN_TIME (min) / STOP_EVENTS
```

### MTBF (Mean Time Between Failures)

**Definition:** Average uptime duration between stops.

**Formula:**
```
MTBF (min) = PRODUCTION_TIME (min) / STOP_EVENTS
```

**Interpretation:**
- Higher MTBF = More stable production (longer runs between failures)
- Lower MTBF = Frequent interruptions

---

## 🏗️ Risk Tower Logic

The Risk Tower ranks equipment run rate risks over a rolling 4-week window.

### Weekly Metrics Calculation
- Data is grouped by Equipment and ISO Week
- Stability Index, MTTR, MTBF calculated per week
- Weeks with zero production are ignored

### Trend Calculation
- Compares **First Active Week** vs **Last Active Week**
- **Decline Flag:** Triggered if stability dropped > 5%:
  ```
  (first_week - last_week) / first_week > 0.05
  ```

### Risk Scoring (0-100)
```
Base Score = Stability Index for the 4-week period
Penalty: If Decline Flag is TRUE → Subtract 20 points
Risk Score = max(0, min(100, Base Score - Penalty))
```

### RAG Status
| Status | Condition              |
|--------|------------------------|
| Red    | Stability < 50%        |
| Amber  | 50% ≤ Stability < 70%  |
| Green  | Stability ≥ 70%        |

### Primary Risk Factor Identification (Priority Order)
1. **"Declining Trend"** - If the Trend Penalty was applied
2. **"High MTTR"** - If Stability < 70% AND MTTR > 1.2× average
3. **"Frequent Stops"** - If Stability < 70% AND MTBF < 0.8× average
4. **"Critical Stability"** - If Stability < 50% (Red Status)
5. **"Moderate Stability"** - If 50% ≤ Stability < 70% (Amber Status)
6. **"Stable"** - If Stability ≥ 70% (Green Status)

**Code Location:** `core/risk_tower.py`

---

## 📊 Excel Report Structure

The Excel report contains 3 sheets:

### Sheet 1: Production Report
- Equipment information header
- Production metrics summary
- Shot-by-shot data table with:
  - STOP flag and STOP_TYPE
  - Cumulative production time
  - Run duration calculations
  - Time buckets

### Sheet 2: Trends & Graphs
- Daily aggregated metrics
- MTTR/MTBF trends
- Efficiency trends over time
- Production vs downtime charts

### Sheet 3: Risk Tower
- Equipment risk rankings
- 4-week rolling window analysis
- RAG status visualization
- Primary risk factors
- Trend change indicators

---

## 📐 Mathematical Relationships

### Time Balance Equation
```
TOTAL_RUN_TIME ≈ PRODUCTION_TIME + TOTAL_DOWN_TIME
```

### Efficiency vs Stability
- **Efficiency:** Based on shot count (Normal Shots / Total Shots)
- **Stability:** Based on time (Production Time / Total Run Time)

These can differ if stopped shots have different durations than normal shots.

---

## 🎯 Example Calculation

### Scenario:
- Session with 100 shots
- 90 normal shots, 10 stopped shots
- 3 stop events (consecutive stops counted as 1)
- Production time: 450 minutes
- Downtime: 50 minutes
- Total run time: 500 minutes

### Calculations:

**Efficiency:**
```
Efficiency = (90 / 100) × 100 = 90%
```

**Stability Index:**
```
Stability = (450 / 500) × 100 = 90%
```

**MTTR:**
```
MTTR = 50 min / 3 events = 16.67 minutes per stop
```

**MTBF:**
```
MTBF = 450 min / 3 events = 150 minutes between stops
```

---

## 📝 Configuration Parameters

| Parameter                  | Default    | Description                                    |
|---------------------------|------------|------------------------------------------------|
| Run Interval Threshold    | 8 hours    | Gaps > this create new runs                    |
| Mode CT Tolerance         | ±5%        | Band for normal cycle time                     |
| Downtime Gap Tolerance    | 2.0 sec    | Added to CT for time gap detection            |
| Risk Trend Threshold      | 5%         | Decline % to trigger trend flag               |
| Risk Trend Penalty        | 20 points  | Points deducted for declining trend           |
| High MTTR Multiplier      | 1.2×       | MTTR > 1.2× avg = High MTTR                   |
| Low MTBF Multiplier       | 0.8×       | MTBF < 0.8× avg = Frequent Stops              |
| Stability Critical        | 50%        | Below this = Red status                        |
| Stability Moderate        | 70%        | Below this = Amber status                      |

---

## 📚 References

- **Main Implementation:** `analysis/runrate/core/session_analyzer.py`
- **Risk Tower Logic:** `analysis/runrate/core/risk_tower.py`
- **Excel Output:** `analysis/runrate/reporting/excel_generator.py`
- **Risk Tower Sheet:** `analysis/runrate/reporting/excel_risk_tower.py`

---

**Version History:**
- 2.6 (2026-02-03): Added first shot handling logic, Risk Tower as 3rd sheet
- 2.0 (2025-12-02): Aligned with Dashboard Specification
