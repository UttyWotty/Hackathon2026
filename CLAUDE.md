# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server (port 3020, auto-reload in dev mode)
python main.py

# Start supporting services (Redis cache + Langfuse observability)
docker-compose up -d

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_job_queue.py -v

# Run pipeline tests only
pytest tests/pipelines/ -v

# Run a specific test function
pytest tests/test_error_handling.py::test_function_name -v

# Lint / format (pinned versions; enforced in CI via .github/workflows/ci.yaml)
ruff check .
black --check .
isort --check-only .

# Helper scripts (kill port 3020 if held, then start)
./start_server.sh      # start (fails if port in use)
./restart_server.sh    # kill existing process + start fresh
./stop_server.sh
```

The start/restart scripts source `preflight.sh` first, which verifies the chosen interpreter has core dependencies (fails loudly instead of silently disabling routers). Override the interpreter with `PYTHON=/opt/anaconda3/bin/python ./start_server.sh` -- use a fully-provisioned env; a bare Python missing sqlalchemy et al. disables ~14 routers via graceful degradation.

Version is tracked in the top-level `VERSION` file. Deployment is separate from CI: `.github/workflows/dev-deploy.yaml` builds a Docker image and pushes to AWS ECR on push to the `dev-deploy` branch (the `Dockerfile` is not checked in).

Environment setup: copy `COPY_TO_ENV.txt` to `.env` and fill in Snowflake credentials + optional service keys. All env vars have explicit defaults declared as module-level constants.

Entry points once running: Swagger UI at `/docs`, ReDoc at `/redoc`, health at `/health`, MCP protocol info at `/mcp/info`. Port is `SERVER_PORT` (default 3020).

Reference docs in `docs/`: `MCP_PROTOCOL.md` (MCP tool contract), `runrate_llm_prompts.md` (RunRate LLM prompt specs), `tech_debt.md` (active tech-debt list -- wrap resolved lines in `<!-- -->` when fixing, per convention below).

## Architecture

**Single FastAPI server** on port 3020. No microservices -- everything runs in one process.

### Layer Hierarchy (strict import direction)

```
middleware/       --> Rate limiting, input validation, request context (applied in main.py)
  |
routers/          --> API endpoints (~26 routers registered in main.py via try/except; plus helper modules like email_helpers.py, mcp_tool_utils.py, websocket_chat.py)
  |
services/         --> Business logic + infrastructure adapters
  |-- infrastructure/   --> I/O adapters: snowflake, cache, ml, email, jobs, scheduler, monitoring, audit, auth, backup, documents, google_chat, observability, transformation
  |-- config/features/  --> Analytics pipeline configs and implementations (analytics, insights, sql)
  |-- sales_report/, visualization/
  |
analysis/         --> Standalone analysis modules: capacity, ct_deviation, ct_efficiency, insights, rca, roi, runrate, tooling_eol (shared/ holds common helpers)
  |
core/             --> Tool definitions (tools_config.py), LLM client, prompts, token tracking
models/           --> SQLAlchemy models + SQLite migrations (audit, users, scheduler, notifications, etc.)
utils/            --> Cross-cutting utilities (error_handling, sql_validation, input_validation, redaction)
```

Lower layers never import from higher layers. Routers call services; services call analysis/pipelines.

### Key Infrastructure Patterns

**Snowflake sessions:** Use `services/infrastructure/snowflake/session_pool.py`. Access via `get_session_pool()` singleton. Supports multi-database (main + raw), read-only query validation, and connection pooling.

**Caching:** `services/infrastructure/cache/unified_cache.py` -- Redis primary with automatic LRU in-memory fallback. Tag-based invalidation. Redis is optional (system works without it).

**ML/LLM:** Two paths. (1) Primary chat + tool-calling runs on **AWS Bedrock Claude** via `core/llm_client.py` (`BedrockClient`, model from `BEDROCK_MODEL_ID`, optional `AWS_BEARER_TOKEN_BEDROCK`); tool definitions are formatted for the Bedrock Converse API in `core/tools/bedrock_adapter.py`, and used by `routers/chat_router.py` / `routers/websocket_chat.py`. (2) Local inference via MLX (`services/infrastructure/ml/mlx_llm.py`) with Qwen3-32B, QwQ-32B, Qwen2.5-Coder, Llama-3.2-3B. Embeddings via sentence-transformers (`ml/embeddings.py`).

**Observability:** Optional Langfuse integration (`services/infrastructure/observability/`). Gracefully degrades when disabled.

**Background jobs:** Async job queue (`services/infrastructure/jobs/job_queue.py`) with status tracking and 24-hour auto-cleanup. Cron scheduler in `services/infrastructure/scheduler/`.

### Analytics Pipelines

Located in `services/config/features/analytics/pipelines/`. Each pipeline (run_rate, roi, ana_shot_made, master_shot_table) follows a standard structure: `config.py`, `data_fetcher.py`, `calculations.py`, `table_manager.py`, `uploader.py`, `main.py`. Base classes in `base_pipeline.py`, `base_table_manager.py`, `base_uploader.py`.

RunRate calculation spec: see `analysis/runrate/CALCULATION_SPEC.md` (SESSION_GAP_HOURS=8, stop detection logic, MTTR/MTBF formulas).

### Router Registration

All routers are registered in `main.py` via individual try/except blocks. Each router failure is logged but does not prevent server startup (graceful degradation).

### Lifespan

Uses FastAPI `lifespan` async context manager (not deprecated `@app.on_event`). Startup initializes: SQLite database + migrations, background scheduler, health monitor, email queue processor, Langfuse client.

### Testing

pytest with `pytest-asyncio`. Config lives in `pytest.ini` (`pythonpath = .`, `addopts = -ra`). Session-scoped `TestClient` fixture in `tests/conftest.py` (imports `main:app` directly, no external server needed). Pipeline-specific fixtures in `tests/pipelines/*/conftest.py`.

CI (`.github/workflows/ci.yaml`) does NOT run the full suite: it excludes pipeline/integration tests via `--ignore=tests/pipelines` and `-k "not snowflake and not redis and not langfuse and not langflow"` (Python 3.10/3.11/3.12 matrix). Run `pytest tests/pipelines/ -v` locally to cover what CI skips.

## Project-Specific Conventions

### Dependency Injection for I/O
Classes using I/O adapters (e.g., `SnowflakeConnectionManager`) MUST accept them as optional constructor parameters:
```python
def __init__(self, ..., connection_manager: Optional[SnowflakeConnectionManager] = None):
    self.connection_manager = connection_manager or SnowflakeConnectionManager(...)
```
The instance variable is always named `connection_manager` (never `conn_manager`, `cm`, or `manager`).

### Logging
Use `%s`-style lazy formatting: `logger.info("Processed %d records for %s", count, client)` -- never f-strings in logger calls.

### Environment Variables
All reads must have explicit defaults as module-level constants:
```python
POOL_WARMUP_SIZE = int(os.getenv("POOL_WARMUP_SIZE", "2"))
```
No inline `os.getenv()` buried in function bodies.

### Tech Debt Tracking
When fixing items from `docs/tech_debt.md`, wrap resolved lines in `<!-- -->` HTML comments to preserve history.

## Code Rules

1. **500-Line Shield** -- No file exceeds 500 lines. Propose refactoring before writing if it would.
2. **Mandatory Docstrings** -- Every file starts with a 3-sentence summary (used for RAG).
3. **Atomic Responsibility** -- One thing per file (SRP).
4. **No Emojis** -- Forbidden in code, comments, docstrings, markdown, commits, explanations.
5. **Explicit Interfaces** -- Full type hints on all public functions/classes. Use TypedDict or dataclass when unclear.
6. **Function Size Limit** -- Max ~50 lines per function; extract helpers.
7. **I/O Separation** -- Pure business logic isolated from database/filesystem/network.
8. **Explicit Defaults** -- All defaults declared and documented.
9. **Domain-Specific Errors** -- No generic exceptions; define domain exception classes.
10. **No Dead Code** -- Commented-out code is forbidden.
11. **Named Constants** -- No magic numbers or strings.
12. **Import Direction** -- Lower-level modules never import higher-level modules.
13. **Testing** -- All pure logic modules must have tests (no I/O, no mocks unless unavoidable).
14. **Rule Precedence** -- Correctness > Atomic Responsibility > 500-Line Shield > Explicit Interfaces > Style.
