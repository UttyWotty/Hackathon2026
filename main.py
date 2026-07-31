"""
Cortex Workflow Agent - Unified Server.

Single FastAPI application hosting the autonomous manufacturing workflow agent and the
analytics tools it reasons with, all on port 3020. The agent senses anomalies in shot-level
manufacturing data, reasons over them with an LLM, and chains multi-step actions autonomously.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from middleware.rate_limiter import RateLimitMiddleware

load_dotenv()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Create logs directory before configuring file handler
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/cortex_agent.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Server configuration constants
SERVER_PORT = int(os.getenv("SERVER_PORT", "3020"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3020"
)

VERSION_FILE = project_root / "VERSION"
APP_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "0.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown: database init and background scheduler."""
    import asyncio

    from services.infrastructure.scheduler.background_scheduler import (
        start_scheduler,
        stop_scheduler,
    )

    logger.info("Cortex Workflow Agent starting...")

    # Initialize database
    try:
        from models.database import get_database_info, init_database

        if init_database():
            db_info = get_database_info()
            logger.info("Database ready: %s", db_info["database_path"])
        else:
            logger.warning("Database initialization failed")
    except Exception as e:
        logger.warning("Database initialization error: %s", e)

    # Start background scheduler
    scheduler_task = None
    try:
        scheduler_task = asyncio.create_task(start_scheduler())
        logger.info("Background scheduler started")
    except Exception as e:
        logger.error("Scheduler startup failed: %s", e)

    logger.info("Cortex Workflow Agent ready on port %d", SERVER_PORT)

    yield

    # Cleanup
    logger.info("Cortex Workflow Agent shutting down...")
    if scheduler_task:
        stop_scheduler()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error("Scheduler shutdown error: %s", e)


# Create FastAPI application
app = FastAPI(
    title="Cortex Workflow Agent",
    description="""
    # Cortex Workflow Agent

    An autonomous manufacturing workflow agent. It senses anomalies in shot-level
    production data, reasons over them with an LLM, and chains multi-step actions
    without waiting for a human turn.

    ## Surfaces

    - **Scheduler**: cron jobs and background job queue, the agent's trigger
    - **MCP**: tool contract exposed over the Model Context Protocol

    ## Quick start

    1. `GET /health` to confirm the server is up
    2. `GET /mcp/mcp/info` for the tool contract
    3. Run `scripts/run_agent.py` to trigger the autonomous agent

    Built for the Snowflake CoCo CLI Hackathon 2026.
    """,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(RateLimitMiddleware, default_limit=RATE_LIMIT_DEFAULT)

allowed_origins = [o.strip() for o in CORS_ALLOWED_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors gracefully."""
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)

    if ENVIRONMENT == "production":
        error_message = "An internal error occurred."
        error_type = "InternalError"
    else:
        error_message = str(exc)
        error_type = type(exc).__name__

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": error_message,
            "error_type": error_type,
            "path": request.url.path,
        },
    )


@app.get("/")
async def root():
    """API information and available endpoints."""
    return {
        "service": "Cortex Workflow Agent",
        "version": APP_VERSION,
        "status": "running",
        "environment": ENVIRONMENT,
        "documentation": f"http://localhost:{SERVER_PORT}/docs",
        "surfaces": [
            "Scheduler (job management and agent triggers)",
            "MCP (Model Context Protocol tool exposure)",
            "Health check",
        ],
        "agent_entry_point": "python scripts/run_agent.py",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint. Returns server status and system information."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server": {
            "port": SERVER_PORT,
            "environment": ENVIRONMENT,
            "python_version": sys.version.split()[0],
        },
    }


# ============================================================================
# Routers
# ============================================================================

try:
    from routers.scheduler_router import router as scheduler_router

    app.include_router(scheduler_router, prefix="/scheduler", tags=["Scheduler"])
    logger.info("Scheduler router registered")
except ImportError as e:
    logger.warning("Scheduler router not found: %s", e)

try:
    from routers.mcp_router import router as mcp_router

    app.include_router(mcp_router, prefix="/mcp", tags=["MCP Protocol"])
    logger.info("MCP router registered")
except ImportError as e:
    logger.warning("MCP router not found: %s", e)


# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Cortex Workflow Agent - http://%s:%d", SERVER_HOST, SERVER_PORT)
    logger.info("=" * 60)

    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=(ENVIRONMENT == "development"),
        log_level="info",
    )
