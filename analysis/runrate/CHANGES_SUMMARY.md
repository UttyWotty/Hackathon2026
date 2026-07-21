# RunRate Calculation Changes Summary

## Date: 2025-12-02

---

## ✅ Changes Made

### 1. **MTBF Calculation - FIXED**

**Previous Implementation (INCORRECT):**
```python
# Complex interval-based calculation
# Calculated average time BETWEEN consecutive failures using RUN_DURATION
# Multiple edge cases for single/multiple failures
```

**New Implementation (SPEC-COMPLIANT):**
```python
# Simple formula matching industry standard
MTBF (min) = Production Time (min) / Stop Events

# Code:
if stop_events > 0:
    mtbf_min = (prod_time_sec / 60) / stop_events
```

**File Changed:** `analysis/runrate/core/session_analyzer.py` (lines 411-443)

**Why This Change:**
- Matches the specification exactly
- Simpler and more intuitive
- Standard industry calculation
- Easier to understand and maintain

---

## ✅ Verified (No Changes Needed)

### 2. **Total Run Duration - CORRECT**

**Formula:**
```
TOTAL_RUN_TIME (min) = [Σ SHOT_DIFF_SEC + MODE_CT] / 60
```

**Implementation:**
- ✅ Correctly sums shot intervals within sessions
- ✅ Excludes first shot's interval (pre-session break)
- ✅ Adds mode CT for last shot
- ✅ Sessions split at 8h+ gaps (excludes idle time)

**Location:** `session_analyzer.py` lines 288-292

---

### 3. **Downtime Duration - CORRECT**

**Formula:**
```
TOTAL_DOWN_TIME (min) = Σ SHOT_DIFF_SEC (for stopped shots) / 60
```

**Implementation:**
- ✅ Uses `SHOT_DIFF_SEC` for all stopped shots
- ✅ Excludes first shot's interval
- ✅ Captures both abnormal cycles and time gaps

**Location:** `session_analyzer.py` lines 313-325

---

### 4. **MTTR Calculation - CORRECT**

**Formula:**
```
MTTR (min) = Total Downtime (min) / Stop Events
```

**Implementation:**
```python
if stop_events > 0:
    mttr_min = (downtime_sec / 60) / stop_events
```

**Location:** `session_analyzer.py` lines 435-438

✅ Already matches spec exactly!

---

## 📊 Impact Analysis

### What Changed:
- **MTBF values will be DIFFERENT** (simplified calculation)
- All other metrics remain unchanged

### Expected Behavior:
- MTBF now represents: "Average production time per stop event"
- More intuitive interpretation
- Easier to benchmark and compare

### Example Comparison:

**Scenario:** 
- Production Time: 480 minutes
- Stop Events: 12

**Old MTBF (interval-based):** 
- Varied based on when stops occurred
- Could be 35-45 minutes depending on distribution

**New MTBF (spec-compliant):**
- 480 / 12 = **40 minutes**
- Consistent and predictable

---

## 📁 Files Modified

1. ✅ `analysis/runrate/core/session_analyzer.py`
   - Updated `_calculate_maintenance_metrics()` function
   - Simplified MTBF calculation
   - Updated docstrings

2. ✅ `analysis/runrate/CALCULATION_SPEC.md` (NEW)
   - Complete documentation of all calculations
   - Formulas, examples, and code locations
   - Reference guide for future maintenance

3. ✅ `analysis/runrate/CHANGES_SUMMARY.md` (THIS FILE)
   - Summary of changes made
   - Impact analysis

---

## 🧪 Testing Recommendations

1. **Run existing runrate analysis** and compare outputs
2. **Verify MTBF values** make sense (should be production_time / stop_events)
3. **Check Excel reports** - MTBF column should show new values
4. **Validate against spec** - confirm formulas match expectations

---

## 📚 Documentation

All calculations are now documented in:
- **`CALCULATION_SPEC.md`** - Complete calculation reference
- **Code comments** - Inline documentation in `session_analyzer.py`

---

## ✅ Verification Checklist

- [x] MTBF calculation matches spec formula
- [x] MTTR calculation matches spec formula
- [x] Total Run Duration logic verified
- [x] Downtime Duration logic verified
- [x] Documentation created
- [x] No linter errors
- [x] Changes committed to codebase

---

## 🎯 Summary

**Bottom Line:** Your RunRate calculations now **exactly match** the specification. The main change was simplifying the MTBF calculation to use the industry-standard formula: `Production Time / Stop Events`.

All other calculations were already correct and align with the spec's "run-based" analysis approach (excluding 8h+ gaps, using session-level metrics, etc.).

