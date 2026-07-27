# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this repository is

An autonomous manufacturing workflow agent, built for the Snowflake CoCo (Cortex Code) CLI
Hackathon 2026. The agent runs headless on a trigger rather than a human chat turn: it senses
anomalies in manufacturing data, reasons over them with an LLM, autonomously chains multi-step
actions (root-cause analysis, report generation, notification, follow-up scheduling), and records
a decision trail.

It began as a working-tree copy of an internal manufacturing analytics API, with no inherited git
history. It is not that system and must never be confused with it. Roughly 30,000 lines of routers,
pipelines and services were removed to leave only the demo surface.

### Two hard rules

1. **This repository is published as part of a public contest submission.** No real client name,
   supplier roster, equipment code, credential, or client data may ever enter it or its history.
   The original codebase carried 14 real client names, a 190-entry roster of real supplier
   companies and plant locations, and real equipment codes. All were replaced with fictional
   equivalents. Before adding anything derived from the internal system, check it the same way.
2. **All data is synthetic.** Never point this code at a production Snowflake account. It targets
   a hackathon trial account with a generated dataset.

## Build and run

```bash
pip install -r requirements.txt

# Start the server (port 3020)
python main.py
./start_server.sh          # or: ./restart_server.sh, ./stop_server.sh

# Demo UI (port 8501, override with DEMO_PORT)
LOCAL_DATA_DIR=./synthetic_out ./start_demo.sh
streamlit run demo/app.py       # same thing without the preflight

# Tests (724 collected across both suites: 684 application, 40 generator)
pytest tests/ -v                       # application suite
pytest synthetic_data/tests/ -v        # generator suite (pure, no I/O)
pytest tests/test_tool_dispatcher.py -v                        # one file
pytest tests/test_tool_dispatcher.py::test_name -v             # one test
pytest tests/ -k "dispatcher and not snowflake" -v             # by expression

# Lint. Versions are pinned in CI; install the same ones or formatting
# checks drift as new tool releases change the default style.
pip install ruff==0.15.16 black==26.5.1 isort==8.0.1
ruff check . && black --check . && isort --check-only .

# Generate the synthetic dataset
python -m synthetic_data.generate --output-dir ./synthetic_out
python -m synthetic_data.generate --database MMS_DEMO --schema PUBLIC --load
```

CI runs both suites as separate steps and currently covers all 724 tests:

```bash
pytest tests/ -v --tb=short -x -k "not snowflake and not redis and not langfuse and not langflow"
pytest synthetic_data/tests/ -v --tb=short
```

The `-k` filter matches nothing today - no test name contains those substrings, so the
application step collects all 684 either way. It is a guard for the future, not an active
exclusion: the workflow's `env:` block blanks `SNOWFLAKE_*` and `REDIS_URL`, so an integration
test named after one of those services would fail in CI without it. Do not read the filter as
evidence that integration paths are being skipped, and do not delete it as dead weight.

The generator step carries `if: ${{ !cancelled() }}` because the application step uses `-x`.
Without it, one early application failure would abort the run before the generator suite
reported at all.

Use a fully provisioned interpreter. A bare Python missing sqlalchemy and friends will silently
disable routers rather than fail (see Graceful degradation below). `preflight.sh` exists to catch
exactly that: `start_server.sh` and `restart_server.sh` source it, and it hard-fails when fastapi,
uvicorn, pandas, sqlalchemy or snowflake.snowpark are missing (it only warns for the optional
sentence_transformers, email_validator, pptx and redis). Override the interpreter with the
`PYTHON` variable rather than editing the scripts:

```bash
PYTHON=/opt/anaconda3/bin/python ./start_server.sh
```

Entry points once running: Swagger at `/docs`, ReDoc at `/redoc`, health at `/health`,
MCP info at `/mcp/mcp/info` - the doubled segment is real, since `mcp_router` declares its own
`/mcp/*` paths and is then mounted under the `/mcp` prefix. Port is `SERVER_PORT` (default 3020).

Environment: copy `COPY_TO_ENV.txt` to `.env` and fill in the hackathon Snowflake credentials.
`.env` is gitignored and must stay that way.

## Architecture

Single FastAPI application on port 3020. No microservices.

```
middleware/     Rate limiting only (RateLimitMiddleware), applied in main.py
  |
routers/        8 include_router calls over 7 prefixes: /analytics /chat /config
                /email /mcp /monitoring /scheduler. websocket_chat shares the
                /chat prefix with chat_router.
  |
services/       Business logic and I/O adapters
  |-- workflow/        The autonomous agent: controller, sense, scoring, trail
  |-- infrastructure/  snowflake, cache, jobs, scheduler, email, auth, audit,
  |                    observability, google_chat
  |-- config/features/ analytics, insights, sql  (tool implementations)
  |-- visualization/
  |
analysis/       capacity, ct_deviation, ct_efficiency, insights, rca, roi,
                runrate, tooling_eol  (shared/ holds common helpers,
                local_source.py and shot_filters.py serve the offline dataset)
  |
core/           LLM clients (cortex, mlx), backend factory, prompts, tool
                definitions, wire adapters, token tracking
models/         SQLAlchemy models + SQLite (audit, scheduler, email, monitoring,
                workflow, decision_trail)
utils/          error_handling, input_validation, sql_validation
synthetic_data/ The generated dataset this project runs against
scripts/        smoke_llm.py (one backend call), run_agent.py (one agent run)
demo/           Streamlit demo UI. Imports downward only; nothing imports it
```

### The autonomous agent

`services/workflow/controller.py` runs headless on a trigger: sense sweep, LLM reasoning,
tool calls through the existing dispatcher, every step written to a decision trail.
`scripts/run_agent.py` is the entry point and self-grades the run.

Three things about it are non-obvious and were each learned by a run going wrong:

**The sense sweep derives its own follow-ups.** `run_runrate_analysis` has no wildcard: passing
`equipment_codes: ["*"]` returns zeros rather than erroring, which silently fed the model an
all-healthy picture. The opening sweep is CT deviation plus Risk Tower; run rate then follows up
on the machines those name. Never reintroduce a wildcard.

**Grade recorded actions, not prose.** Models narrate work they did not do - observed twice, with
invented MTTR figures and a date range outside the dataset window, while `act steps` was zero.
`services/workflow/scoring.py` reads what was actually invoked from act-step payloads and reports
anything claimed but not backed as `claimed_only`. The trail is the record; the summary is a claim.

**Store the conclusion, not the scratchpad.** Reasoning models put the answer last, so truncating
a summary from the head keeps the deliberation and discards the verdict. Run summaries strip
`<think>` blocks (including unterminated ones) and truncate keeping the tail.

Lower layers never import higher ones. Routers call services; services call analysis.

### The demo UI

`demo/` is a Streamlit app in four parts: `app.py` lays out three tabs, `runner.py` is the only
module that touches the database, the network or the filesystem, and `presenters.py` and
`story.py` are pure and tested. Nothing outside `demo/` imports it, so the demo can never affect
the API.

Two things to know before changing it:

**An empty Act group is rendered, not hidden.** A run that reasoned at length and never acted is
the exact failure this project exists to expose, so `group_steps_by_phase` always returns all
three phases. Do not "tidy" it into skipping empty groups.

**Weekly buckets are `W-SUN`, not `W-MON`.** Pandas names a weekly period by the day it *ends*
on, so a Monday-to-Sunday week is `W-SUN`. `W-MON` shifts every bucket back a day and splits a
production week across two points. A test covers this; it was written because the obvious-looking
constant was wrong.

Verify a UI change by executing the script, not by curling the port: Streamlit serves HTTP 200
from a shell that has not yet run your code, and script errors only surface over the websocket.
`streamlit.testing.v1.AppTest.from_file("demo/app.py").run()` runs it and exposes `.exception`.

### The data model

Everything reads one denormalised fact table, `MASTER_SHOT_TABLE`: one row per injection-moulding
shot, carrying cycle time (`CT`), approved cycle time (`APPROVED_CT`), timestamp
(`LOCAL_SHOT_TIME`), equipment, supplier, part and tooling attributes.

There is deliberately **no derived `RUNRATE` table**. The upstream system precomputed one, but the
run-rate analysis reads `MASTER_SHOT_TABLE` directly, and the derived table's only consumers
queried column names the pipeline never created. All analytics run off the fact table. Only the
`master_shot_table` pipeline is kept; `roi`, `ana_shot_made` and `run_rate` were removed.

RunRate calculation spec: `analysis/runrate/CALCULATION_SPEC.md` (8-hour session gap, stop
detection order, MTTR/MTBF). The synthetic generator is built against that spec and
`synthetic_data/tests/runrate_reference.py` re-implements it independently to verify the data.

### Running without Snowflake

Set `LOCAL_DATA_DIR=./synthetic_out` and the four `fetch_*` seams serve `MASTER_SHOT_TABLE` from
the generator's CSVs instead of querying Snowflake. Empty (the default) means Snowflake, so
production behaviour is unaffected. `analysis/shared/shot_filters.py` holds the predicates as
pure functions; `analysis/shared/local_source.py` does the file I/O.

**The four analyses do not share predicates, and the differences are load-bearing.** Anything
touching these must preserve them or local results will silently disagree with Snowflake:

| Analysis | Row filter | End-date bound |
|---|---|---|
| `ct_deviation` | `CT > 0`, `APPROVED_CT > 0`, `CT < 999.9` | `<= end 23:59:59` |
| `ct_efficiency` | same as above | `<= end` (midnight - excludes the end day) |
| `runrate` | `VOLUME > 0` only; **keeps sentinel CT** | `<= end 23:59:59`, lower bound on shot END |
| `capacity` | `CT < 999.9` and `VOLUME > 0` | `< end + 1 day` |

Two traps in particular. Run rate must keep `CT >= 999.9` rows because stop detection is derived
from them - filtering them out silently erases downtime. And `<= '23:59:59'` is not the same as
`< the next day`: shot timestamps carry milliseconds, so a shot at `23:59:59.5` falls outside the
SQL bound but inside a naive day-boundary rewrite.

### Tool dispatch is dynamic - read this before deleting anything

`services/infrastructure/scheduler/tool_dispatcher.py` maps ~35 tool names to
`(module_path, function_name)` string pairs and resolves them with `__import__` at call time.

**Static analysis cannot see these edges.** An import graph will report every sense tool
(`analysis/rca`, `analysis/runrate`, and the rest) as unreachable dead code. Seed any dependency
analysis from `_TOOL_IMPORTS` or you will delete the heart of the application.

Package re-exports hide edges too: `core/tools/__init__.py` re-exports `bedrock_adapter`, and
`routers/__init__.py` re-exports `analytics_router`. Both look unreachable and are load-bearing.

If you remove a tool, remove its dispatcher entry **and** its definition in
`core/tools/definitions/`, or the model will be offered a tool that cannot run.

### Graceful degradation, and why it hides mistakes

`main.py` registers each router inside `try/except ImportError` and logs a warning on failure.
A broken import therefore does not crash the server - it silently drops the router.

**Never conclude the app is healthy because it starts.** Check the route count:

```bash
python -c "import main; print(len(main.app.routes))"   # expect 67
```

A previous trim broke `routers/__init__.py`, which made all eight routers fail to import. The
server started cleanly with 9 routes instead of 67 and logged only warnings.

67 counts a clean startup with **no** router warnings. It did not always: `main.py` used to
mount a `/database` router by importing `snowflake_router`, which the trim had already deleted,
so every startup logged `Database router not found` and 67 silently described a degraded app.
That dead block is now removed and the count is unchanged, which is the proof it never mounted.

The lesson generalises: a warning that is always present trains you to ignore the warnings that
matter. If a router warning is ever expected, fix the cause rather than documenting the noise.

### LLM

The client is chosen by a factory, `core/llm_backend.py` `get_llm_client`, keyed on the
`LLM_BACKEND` env var. It returns a `CortexClient` (`core/cortex_client.py`, the default and the
submission path) talking to the Cortex REST Messages API (`POST /api/v2/cortex/v1/messages`,
Anthropic wire format, PAT bearer auth), or an `MLXClient` (`core/mlx_client.py`) for local
development against `mlx_lm.server` on Apple Silicon. Both return responses in the Anthropic shape,
parsed by the pure `core/cortex_wire.py` / `core/mlx_wire.py` modules, so callers never branch on
backend. Cortex tool schemas are formatted by `core/tools/cortex_adapter.py`. Consumed by
`core/chat_interface.py`, `routers/chat_router.py` and `routers/websocket_chat.py` (the latter two
via `get_traced_llm_client`), and by the workflow controller.

**The Bedrock port is done.** `core/llm_client.py` `BedrockClient` and `core/tools/bedrock_adapter.py`
remain in the tree but are no longer wired into any call site; the factory offers only Cortex and
MLX. See `HACKATHON_PLAN.md` Appendix A for the verified Cortex request and response shapes. What
is still untested is first contact against a live account: PAT auth, the exact GA Claude model id,
and the PUT/COPY dataset load have only run against synthetic CSVs and the MLX backend.

### Lifespan

FastAPI `lifespan` async context manager, never the deprecated `@app.on_event`. Startup
initialises the SQLite database, the background scheduler, the email queue processor, and
optionally Langfuse.

## Synthetic data

`synthetic_data/` generates a reproducible, client-free dataset matching the `MASTER_SHOT_TABLE`
contract: 8 machines across 5 behavioural archetypes, about 230,000 shots over 6 weeks, plus
`MOLD`, `COMPANY`, `LOCATION`, `PART` and `WORK_ORDER`.

Every defect is planted deliberately and declared in a `ground_truth.json` emitted beside the CSVs,
so the agent's autonomous output is scored against a contract rather than a recollection. The demo
headline is `EMA-4103`: its cycle time drifts from 1.9% to 24.0% above approved CT over six weeks
while stability stays at 90%, indistinguishable from healthy machines. A single-metric monitor
cannot see it; catching it requires reasoning across CT deviation and run rate together.

Generation is pure and seeded - no clock access, no I/O outside `loader.py` and `generate.py`.
Read `synthetic_data/README.md` before changing generation: cycle times are quantised to a 0.1s
grid and normal shots have their clock advance clamped, both for reasons that are not obvious and
that the tests will catch you on.

## Testing

pytest with `pytest-asyncio`; config in `pytest.ini` (`pythonpath = .`). Session-scoped
`TestClient` fixture in `tests/conftest.py` imports `main:app` directly, so no external server is
needed. 724 tests currently pass (684 application, 40 generator).

`synthetic_data/tests/` is pure logic with no I/O and no Snowflake. It asserts the dataset against
`CALCULATION_SPEC.md` rather than against the implementation, so it stays honest if the
implementation drifts.

## Code rules

1. **500-Line Shield** - no file exceeds 500 lines; propose a refactor before writing past it.
2. **Mandatory docstrings** - every file starts with a 3-sentence summary (used for RAG).
3. **Atomic responsibility** - one thing per file.
4. **No emojis** - anywhere: code, comments, docs, commit messages, explanations.
5. **Explicit interfaces** - full type hints on public functions and classes.
6. **Function size** - about 50 lines maximum; extract helpers.
7. **I/O separation** - pure logic isolated from database, filesystem and network.
8. **Explicit defaults** - all defaults declared and documented.
9. **Domain-specific errors** - no generic exceptions.
10. **No dead code** - delete it; that is what version control is for.
11. **Named constants** - no magic numbers or strings.
12. **Import direction** - lower-level modules never import higher-level ones.
13. **Testing** - pure logic modules have tests, no mocks unless unavoidable.
14. **Precedence** - correctness > atomic responsibility > 500-line shield > explicit
    interfaces > style.

### Project conventions

**Dependency injection for I/O.** Classes using an I/O adapter accept it as an optional
constructor parameter, and the instance variable is always `connection_manager`:

```python
def __init__(self, ..., connection_manager: Optional[SnowflakeConnectionManager] = None):
    self.connection_manager = connection_manager or SnowflakeConnectionManager(...)
```

**Logging.** Lazy `%s` formatting, never f-strings:
`logger.info("Processed %d records for %s", count, client)`.

**Environment variables.** Every read has an explicit default declared as a module-level constant:
`POOL_WARMUP_SIZE = int(os.getenv("POOL_WARMUP_SIZE", "2"))`. No inline `os.getenv()` in function
bodies.

## Known inherited quirks

- `VERSION` still reads `0.1.9`, carried over from the upstream project. It does not describe this
  repository and should be reset when the submission is tagged.
- `analysis/roi/` survives because `roi_tools.py` imports it, even though the ROI pipeline was
  removed. It is reachable, not orphaned.
- `synthetic_data` maintenance generation produces no `WORK_ORDER` rows for windows shorter than
  its 7-21 day maintenance intervals. Harmless at the 6-week default.
