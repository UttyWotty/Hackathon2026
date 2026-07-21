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

# Tests
pytest tests/ -v                       # application suite
pytest synthetic_data/tests/ -v        # generator suite (pure, no I/O)

# Lint (pinned; enforced in CI)
ruff check . && black --check . && isort --check-only .

# Generate the synthetic dataset
python -m synthetic_data.generate --output-dir ./synthetic_out
python -m synthetic_data.generate --database MMS_DEMO --schema PUBLIC --load
```

Use a fully provisioned interpreter. A bare Python missing sqlalchemy and friends will silently
disable routers rather than fail (see Graceful degradation below).

Entry points once running: Swagger at `/docs`, ReDoc at `/redoc`, health at `/health`,
MCP info at `/mcp/info`. Port is `SERVER_PORT` (default 3020).

Environment: copy `COPY_TO_ENV.txt` to `.env` and fill in the hackathon Snowflake credentials.
`.env` is gitignored and must stay that way.

## Architecture

Single FastAPI application on port 3020. No microservices.

```
middleware/     Rate limiting only (RateLimitMiddleware), applied in main.py
  |
routers/        8 routers, mounted at /analytics /chat /config /database
                /email /mcp /monitoring /scheduler
  |
services/       Business logic and I/O adapters
  |-- infrastructure/  snowflake, cache, jobs, scheduler, email, auth, audit,
  |                    observability, google_chat
  |-- config/features/ analytics, insights, sql  (tool implementations)
  |-- visualization/
  |
analysis/       capacity, ct_deviation, ct_efficiency, insights, rca, roi,
                runrate, tooling_eol  (shared/ holds common helpers)
  |
core/           LLM client, prompts, tool definitions, token tracking
models/         SQLAlchemy models + SQLite (audit, scheduler, email, monitoring, workflow)
utils/          error_handling, input_validation, sql_validation
synthetic_data/ The generated dataset this project runs against
```

Lower layers never import higher ones. Routers call services; services call analysis.

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

### LLM

Currently `core/llm_client.py` `BedrockClient`, talking to AWS Bedrock, with tool schemas formatted
by `core/tools/bedrock_adapter.py`. Consumed by `core/chat_interface.py`, `routers/chat_router.py`
and `routers/websocket_chat.py`.

**The port to Snowflake Cortex is the main outstanding task.** The target is the Cortex REST
Messages API (`POST /api/v2/cortex/v1/messages`), which is the Anthropic wire format and maps
almost verbatim onto the existing loop, authenticated with a Snowflake PAT as a bearer token.
Keep the four parser helpers' contracts stable and the agent loop needs no changes. Add a Cortex
tool-format adapter beside `bedrock_adapter.py`. See `HACKATHON_PLAN.md` Appendix A for the
verified request and response shapes.

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
needed. 500 tests currently pass.

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
