# Synthetic manufacturing dataset generator

Generates a reproducible, client-free manufacturing dataset whose schema matches the production
`DEMO_TABLE` contract, so the existing sense tools run against it unmodified. Every defect
in the data is planted deliberately and declared up front, which turns the hackathon demo into a
verifiable claim instead of an anecdote. Generation is pure and self-contained: this package
must never import from the application it supplies data to.

## Usage

```bash
# Write CSV files plus the ground-truth contract, no Snowflake needed
python -m synthetic_data.generate --output-dir ./synthetic_out

# Same, then create the objects and COPY INTO the hackathon account
export SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=... SNOWFLAKE_WAREHOUSE=...
python -m synthetic_data.generate --database MMS_DEMO --schema PUBLIC --load

# Tests (pure, no I/O, no Snowflake)
pytest synthetic_data/tests/ -v
```

Defaults: 8 equipment, 6 weeks, 5 production days per week, one 8-hour run per day, seed 20260721.
That yields roughly 230,000 shots. All flags are listed by `--help`.

## Tables produced

| Table | Rows (default) | Purpose |
|---|---|---|
| `DEMO_TABLE` | ~230,000 | The central fact table every sense tool reads |
| `MOLD` | 8 | Tool master data; drives tooling_eol remaining-life logic |
| `COMPANY` / `LOCATION` / `PART` | 3 / 2 / 8 | Dimensions the master shot builder denormalises from |
| `WORK_ORDER` | 16 | Completed maintenance events for maintenance-interval analysis |

Downstream analytic tables (`ROI`, `ANA_SHOT_MADE_TABLE`) are deliberately **not**
generated. They are pipeline outputs, so the existing pipelines should build them from this data.
That also makes the pipelines part of the demo rather than something stubbed around.

## Planted defects

Eight machines, five archetypes. Measured values from the default seed:

| Equipment | Archetype | CT deviation | Stability | MTTR | MTBF | Detected by |
|---|---|---|---|---|---|---|
| MX-7103 | ct_drift | **12.7%** (1.9% to 24.0%) | 90.0% | 2.4 | 22.3 | ct_deviation |
| MX-7104 | frequent_stops | 2.1% | 73.6% | 3.7 | **10.5** | anomaly detection |
| MX-7105 | long_repairs | 2.0% | 77.4% | **13.9** | 48.9 | anomaly detection |
| MX-7106 | declining | 2.1% | **53.4%** | 7.8 | 9.6 | stability trend |
| MX-7101/2/7/8 | stable | ~2.1% | 78-92% | ~2.4 | 7-31 | negative controls |

`MX-7103` is the demo headline. Its cycle time drifts from 1.9% to 24.0% above approved CT across
six weeks, crossing the warning threshold in week 3 and critical in week 6 — while its stability
stays at 90.0%, statistically indistinguishable from the healthy machines. A single-metric monitor
misses it entirely. Surfacing it requires reasoning across CT deviation and stability together,
which is precisely the agent behaviour the Workflow Automation Agent track rewards.

Each generation writes `ground_truth.json` next to the CSVs, declaring the expected finding per
machine (detector, metric, direction, threshold). Score the agent's autonomous output against that
file rather than against recollection.

## Design constraints worth knowing before editing

**Cycle times are quantized to a 0.1-second grid, and normal cycles are drawn from a distribution
sharply peaked on the mode.** This is not cosmetic. `MODE_CT` is a *statistical mode*, and the stop
detector classifies anything outside mode +/- 5% as an Abnormal Cycle. With continuous jitter nearly
every CT is unique, the mode becomes arbitrary, and stop classification turns to noise. A flatter
discrete distribution produces mode *ties* in short runs — which is a real failure this suite caught.

**Normal shots have their clock advance clamped below `previous_ct + 2.0`.** Otherwise a normal
shot at the top of the mode band following one at the bottom trips the Time Gap rule and is
misclassified. The clamp is what guarantees intent matches detection.

**Generation is pure; only `loader.py` and `generate.py` touch the outside world.** No module reads
the clock — `generated_at` is injected — so a given seed reproduces byte-identical output.

## Test contract

The test suite asserts the dataset against the specification:

- every generated shot classifies as the stop kind it was tagged with, in every archetype
- each production day forms exactly one run (overnight idle never counted as downtime)
- the modal cycle time is unique per run
- all four stop kinds appear in the dataset
- generation is reproducible for a fixed seed
- each planted defect separates from the fleet by the margin its expected finding declares
- negative controls stay inside tolerance

If the first or last of these fails, the dataset is not fit for the demo regardless of how it looks.

## Open items

- Not yet validated against a live Snowflake account: the `PUT`/`COPY INTO` path is written but
  unexecuted, pending the hackathon account (plan section 7a, CAVEAT 1).
- Work-order volume is thin (16 rows over six weeks). Sufficient for maintenance-interval logic,
  probably too sparse if tooling_eol becomes a demo centrepiece.
- Supplier-to-tooling-family mapping is simplified: `TOOLING_FAMILY` mirrors `TOOLING_TYPE`, matching
  what RCA does today, rather than reproducing the production supplier-family lookup table.
