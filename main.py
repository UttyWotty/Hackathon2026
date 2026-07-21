"""
Cortex Workflow Agent - Unified Server

Single FastAPI application hosting the autonomous manufacturing workflow agent and the
analytics tools it reasons with, all on port 3020. The agent senses anomalies in shot-level
manufacturing data, reasons over them with an LLM, and chains multi-step actions autonomously.

Architecture:
  - Single FastAPI app (no microservices)
  - 8 routers: analytics, chat, config, database, email, mcp, monitoring, scheduler
  - Direct service calls (no HTTP overhead between layers)
  - Analysis modules in analysis/, tool implementations in services/config/features/

Notes for whoever works here next:
  - Start server: python main.py    Docs: http://localhost:3020/docs
  - Routers register inside try/except ImportError, so a broken import drops a router
    silently instead of failing. Verify with the route count, not just a clean startup:
    python -c "import main; print(len(main.app.routes))"  -> expect 67
  - Tools are dispatched dynamically by name; see CLAUDE.md before deleting anything.
  - All data is synthetic. Never point this at a production account.
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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from middleware.rate_limiter import RateLimitMiddleware

# Load environment variables
load_dotenv()

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/cortex_agent.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Server configuration
SERVER_PORT = int(os.getenv("SERVER_PORT", "3020"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Single source of truth for the release version (see the VERSION file, bumped
# on each release/x.y.z branch); fall back to a sentinel if it is ever missing.
VERSION_FILE = project_root / "VERSION"
APP_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "0.0.0"


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.
    Initialize connections and clean up resources.
    """
    logger.info("Cortex Workflow Agent starting...")

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    # Initialize database
    try:
        from models.database import get_database_info, init_database

        logger.info("Initializing database...")
        if init_database():
            db_info = get_database_info()
            logger.info(f" Database ready: {db_info['database_path']}")
            logger.info(f"   Size: {db_info['database_size_mb']} MB")

        else:
            logger.warning(
                "Database initialization failed - some features may not work"
            )
    except Exception as e:
        logger.warning("Database initialization error: %s", e)

    # Start background scheduler and monitoring
    import asyncio

    from services.infrastructure.email.queue_processor import (
        start_email_queue_processor,
        stop_email_queue_processor,
    )
    from services.infrastructure.scheduler.background_scheduler import (
        start_scheduler,
        stop_scheduler,
    )

    scheduler_task = None
    email_queue_task = None

    try:
        logger.info(" Starting background job scheduler...")
        scheduler_task = asyncio.create_task(start_scheduler())
        logger.info(" Background scheduler started")
    except Exception as e:
        logger.error(f" Scheduler startup failed: {e}")

    try:
        logger.info(" Starting email queue processor...")
        email_queue_task = asyncio.create_task(start_email_queue_processor())
        logger.info(" Email queue processor started")
    except Exception as e:
        logger.error(f" Email queue processor startup failed: {e}")

    # Initialize Langfuse observability (optional)
    try:
        from services.infrastructure.observability.langfuse_client import get_langfuse

        langfuse_client = get_langfuse()
        if langfuse_client is not None:
            logger.info("Langfuse observability initialized")
        else:
            logger.info("Langfuse observability disabled or not configured")
    except Exception as e:
        logger.warning("Langfuse initialization skipped: %s", e)

    logger.info("Cortex Workflow Agent ready")
    logger.info("API Documentation: http://localhost:%d/docs", SERVER_PORT)
    logger.info("Interactive API: http://localhost:%d/redoc", SERVER_PORT)

    yield

    # Cleanup
    logger.info("Cortex Workflow Agent shutting down...")

    # Flush Langfuse traces
    try:
        from services.infrastructure.observability.langfuse_client import (
            shutdown_langfuse,
        )

        shutdown_langfuse()
    except Exception as e:
        logger.warning("Langfuse shutdown error: %s", e)

    # Stop scheduler
    if scheduler_task:
        logger.info(" Stopping background scheduler...")
        stop_scheduler()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info(" Scheduler stopped")
        except Exception as e:
            logger.error(f"Scheduler shutdown error: {e}")

    # Stop email queue processor
    if email_queue_task:
        logger.info(" Stopping email queue processor...")
        stop_email_queue_processor()
        email_queue_task.cancel()
        try:
            await email_queue_task
        except asyncio.CancelledError:
            logger.info(" Email queue processor stopped")
        except Exception as e:
            logger.error(f"Email queue processor shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title="Cortex Workflow Agent",
    description="""
    # Cortex Workflow Agent

    An autonomous manufacturing workflow agent. It senses anomalies in shot-level
    production data, reasons over them with an LLM, and chains multi-step actions
    without waiting for a human turn.

    ## Surfaces

    - **Agent**: `/chat` and the WebSocket chat surface drive the tool-calling loop
    - **Analytics**: cycle-time deviation, run rate, root cause, CT efficiency,
      capacity, tooling end-of-life
    - **Database**: read-only Snowflake queries and schema exploration
    - **Scheduler**: cron jobs and background job queue, the agent's trigger
    - **Email**: report delivery and notifications, one of the agent's actions
    - **MCP**: tool contract exposed over the Model Context Protocol
    - **Monitoring**: health checks and metrics

    ## Quick start

    1. `GET /health` to confirm the server is up
    2. `GET /mcp/info` for the tool contract
    3. `POST /chat` to exercise the agent loop

    ## Data

    All data is synthetic and generated by `synthetic_data/`. There is one fact table,
    `MASTER_SHOT_TABLE`, and every analysis reads from it directly. Planted anomalies
    are declared in `ground_truth.json`, so what the agent finds can be checked against
    what was hidden.

    Built for the Snowflake CoCo CLI Hackathon 2026.
    """,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limiting middleware (applies to all routes except health checks)
rate_limit = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
app.add_middleware(RateLimitMiddleware, default_limit=rate_limit)

# Add CORS middleware for browser access
# Get allowed origins from environment (comma-separated)
CORS_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3020"
)
allowed_origins = [origin.strip() for origin in CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Only specified origins allowed
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static files for chat interface
static_path = project_root / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info(" Static files mounted at /static")
else:
    logger.warning(" Static directory not found - chat interface unavailable")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Handle unexpected errors gracefully.

    In production, sanitizes error messages to prevent information leakage.
    In development, shows full error details for debugging.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Send Google Chat alert for 500 errors
    from services.infrastructure.google_chat.alert_sender import (
        send_alert as send_chat_alert,
    )

    send_chat_alert(
        title=f"500 Error: {request.url.path}",
        message=f"Unhandled {type(exc).__name__}: {str(exc)[:500]}",
        severity="critical",
        source="api-exception-handler",
        alert_key=f"500:{request.url.path}",
    )

    # Sanitize error response based on environment
    if ENVIRONMENT == "production":
        # Don't expose internal error details in production
        error_message = "An internal error occurred. Please contact support."
        error_type = "InternalError"
    else:
        # Show full error in development
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


# Root endpoint
@app.get("/")
async def root():
    """
    API information and available endpoints.
    """
    return {
        "service": "Cortex Workflow Agent",
        "version": APP_VERSION,
        "status": "running",
        "environment": ENVIRONMENT,
        "documentation": f"http://localhost:{SERVER_PORT}/docs",
        "features": [
            "Analytics (ROI, RunRate, RCA, CT Efficiency, etc.)",
            "Snowflake SQL queries",
            "Redis caching for performance",
            "Email notifications and templates",
            "Interactive Plotly visualizations",
            "Job scheduling and automation",
            "System monitoring and alerts",
            "Audit logging for compliance",
            "Machine Learning (anomaly detection, forecasting)",
            "Local LLM (MLX: Qwen3, QwQ, Qwen2.5-Coder, Llama 3.2)",
            "Chat Interface (web-based analytics assistant)",
            "Data transformation & quality checks",
            "Backup & disaster recovery",
            "Authentication (disabled by default)",
        ],
        "quick_start": {
            "health_check": f"GET http://localhost:{SERVER_PORT}/health",
            "api_docs": f"http://localhost:{SERVER_PORT}/docs",
            "chat_interface": f"http://localhost:{SERVER_PORT}/chat",
            "example_analysis": f"POST http://localhost:{SERVER_PORT}/analytics/roi",
        },
    }


# Health check
@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns server status and system information.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server": {
            "port": SERVER_PORT,
            "environment": ENVIRONMENT,
            "python_version": sys.version.split()[0],
        },
        "checks": {
            "api": "ok",
            # Add more health checks as needed
            # "database": check_database_connection(),
            # "redis": check_redis_connection(),
        },
    }


# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """
    Server metrics and statistics.
    Use /monitoring/metrics for detailed system metrics.
    """
    return {
        "status": "healthy",
        "message": "For detailed metrics, use /monitoring/metrics endpoint",
        "endpoints": {
            "system_metrics": "/monitoring/metrics",
            "health": "/monitoring/health",
            "dashboard": "/monitoring/dashboard",
        },
    }


# Chat Interface
@app.get("/chat")
async def chat_interface():
    """
    Serve the Manufacturing Analytics Chat Interface.
    Web-based chat for querying all analysis types.
    """
    chat_file = project_root / "static" / "chat.html"
    if chat_file.exists():
        return FileResponse(str(chat_file))
    return JSONResponse(
        status_code=404,
        content={
            "error": "Chat interface not found",
            "hint": "Ensure static/chat.html exists",
        },
    )


# ============================================================================
# Import and register routers
# ============================================================================

# Analytics Router - Core analysis tools
try:
    from routers import analytics_router

    app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
    logger.info(" Analytics router registered")
except ImportError as e:
    logger.warning(f"  Analytics router not found: {e}")

# Database Router - Snowflake queries
try:
    from routers import snowflake_router

    app.include_router(snowflake_router, prefix="/database", tags=["Database"])
    logger.info(" Database router registered")
except ImportError as e:
    logger.warning(f"  Database router not found: {e}")

# Email Router - Email sending and templates
try:
    from routers.email_router import router as email_router

    app.include_router(email_router, prefix="/email", tags=["Email"])
    logger.info(" Email router registered")
except ImportError as e:
    logger.warning(f"  Email router not found: {e}")

# Scheduler Router - Job scheduling
try:
    from routers.scheduler_router import router as scheduler_router

    app.include_router(scheduler_router, prefix="/scheduler", tags=["Scheduler"])
    logger.info(" Scheduler router registered")
except ImportError as e:
    logger.warning(f"  Scheduler router not found: {e}")

# Monitoring Router - Health checks and metrics
try:
    from routers.monitoring_router import router as monitoring_router

    app.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
    logger.info(" Monitoring router registered")
except ImportError as e:
    logger.warning(f"  Monitoring router not found: {e}")

# MCP Router - Model Context Protocol for LLM integration
try:
    from routers.mcp_router import router as mcp_router

    app.include_router(mcp_router, prefix="/mcp", tags=["MCP Protocol"])
    logger.info("MCP router registered (LLM tool integration)")
except ImportError as e:
    logger.warning(f" MCP router not found: {e}")

# Chat Router - HTTP API for chat interface
try:
    from routers.chat_router import router as chat_router

    app.include_router(chat_router, prefix="/chat", tags=["Chat"])
    logger.info("Chat router registered (LLM chat interface)")
except ImportError as e:
    logger.warning(f" Chat router not found: {e}")

# WebSocket Chat Router - Streaming LLM chat
try:
    from routers.websocket_chat import router as websocket_chat_router

    app.include_router(websocket_chat_router, prefix="/chat", tags=["Chat WebSocket"])
    logger.info("WebSocket chat router registered (streaming LLM chat)")
except ImportError as e:
    logger.warning("WebSocket chat router not found: %s", e)

# Config Router - Dynamic prompts and feature flags
try:
    from routers.config_router import router as config_router

    app.include_router(config_router, prefix="/config", tags=["Configuration"])
    logger.info("Config router registered")
except ImportError as e:
    logger.warning("Config router not found: %s", e)


# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Cortex Workflow Agent")
    logger.info("=" * 70)
    logger.info(f" Starting server on http://{SERVER_HOST}:{SERVER_PORT}")
    logger.info(f" API Docs: http://localhost:{SERVER_PORT}/docs")
    logger.info(f" ReDoc: http://localhost:{SERVER_PORT}/redoc")
    logger.info(f" Health: http://localhost:{SERVER_PORT}/health")
    logger.info(f" Chat: http://localhost:{SERVER_PORT}/chat")
    logger.info("=" * 70)

    # Start server
    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=(ENVIRONMENT == "development"),
        log_level="info",
    )
