# Unified Analytics API + MCP Server

**Version**: 2.0  
**Architecture**: Unified FastAPI Server  
**Status**:  Production Ready

A unified analytics API with ML capabilities, data transformation, backup/recovery, monitoring, PowerPoint generation, and asynchronous job processing. Includes MCP (Model Context Protocol) endpoints for LLM integration.

---

##  Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp COPY_TO_ENV.txt .env
# Edit .env with your Snowflake credentials and configuration
```

### 3. Start Server
```bash
python main.py
```

### 4. Access API
- **Swagger UI**: http://localhost:3020/docs
- **ReDoc**: http://localhost:3020/redoc
- **Health Check**: http://localhost:3020/health
- **MCP Protocol Info**: http://localhost:3020/mcp/info

---

##  What's Inside

### **Core Analytics** (8 Modules)
Analytics modules:

- **ROI Analysis** - Cycle time efficiency & cost analysis
- **RunRate Analysis** - MTTR/MTBF, stop detection, downtime tracking
- **Root Cause Analysis (RCA)** - Pareto charts, Five Whys methodology
- **CT Efficiency** - Supplier benchmarking & cycle time analysis
- **CT Deviation** - Process stability & variation monitoring
- **Tooling EOL** - Tool lifecycle prediction & maintenance planning
- **Capacity Planning** - Multi-OEE capacity analysis
- **Master Shot Table** - Foundation data pipeline

### **Infrastructure** (Routers, 100+ Endpoints)

| Router | Purpose | Key Features |
|--------|---------|--------------|
| **Analytics** | Run analyses | ROI, RunRate, RCA, CT, EOL, Capacity, PPT generation |
| **Database** | Snowflake queries | Execute SQL, table info, schema exploration |
| **Cache** | Query caching | Redis + LRU fallback, tag-based invalidation |
| **Email** | Notifications | Templates, attachments, background sending |
| **Visualization** | Charts & graphs | Plotly charts, dashboards, HTML export |
| **Scheduler** | Background jobs | Cron scheduling, retry logic, job management |
| **Monitoring** | Health checks | Metrics, alerts, trend analysis |
| **Audit** | Compliance logs | Action tracking, compliance reports |
| **ML** | AI-powered insights | Anomaly detection, forecasting, predictions |
| **Transformation** | Data quality | Cleaning, validation, ETL pipelines |
| **Backup** | Disaster recovery | Database snapshots, config backup, restoration |
| **Auth** | Security | JWT tokens (disabled by default, toggle-ready) |
| **MCP** | LLM Integration | Model Context Protocol endpoints |
| **Documents** | Document ingestion | Upload, metadata, keyword + semantic search (RAG-ready) |
| **Users** | User management | Profiles, roles, permissions |
| **Projects** | Organization | Project grouping for tasks/notes |
| **Tasks** | Workflow | Kanban-style tasks + time tracking timers |
| **Notes** | Knowledge base | Notes + full-text search |
| **Config** | LLM / server config | DB-backed prompts + feature flags |
| **Notifications** | Notification hub | User notifications + webhook ingestion |

### **PowerPoint Generation** 

Generate professional PowerPoint presentations:

- **Single Analysis PPT**: `/analytics/generate_ppt` - Create PPT from analysis results
  - Supports: RunRate analysis
  - Includes: Executive summary, key metrics, findings, recommendations
- **Weekly Comparison PPT**: `/analytics/generate_weekly_comparison_ppt` - Compare two weeks of data
  - Newsletter-style format
  - Week-over-week percentage changes
  - KPI comparisons (ROI, RunRate, Capacity)
  - Key insights and trends

### **Job Queue System**

Asynchronous background task execution:

- **Submit Jobs**: `/tools/submit` - Submit long-running tasks for background execution
- **Check Status**: `/tools/jobs/{job_id}` - Poll job status and results
- **List Jobs**: `/tools/jobs` - View recent jobs
- **Automatic Cleanup**: Jobs older than 24 hours are automatically removed
- **Status Tracking**: pending → running → completed/failed
- **Health Integration**: Job queue status included in `/health` endpoint

### **Security Features**

- ✅ **CORS Protection** - Configurable allowed origins (no wildcard `*`)
- ✅ **Rate Limiting** - Sliding window algorithm with per-endpoint limits
- ✅ **Request Timeout** - 5-minute timeout middleware (configurable)
- ✅ **Input Validation** - Request size, query length, and file size limits
- ✅ **Secret Management** - `.gitignore` protects `.env`, private keys, databases
- ✅ **JWT Authentication** - Toggle-ready (disabled by default)
- ✅ **Professional Logging** - Structured logging with automatic rotation
- ✅ **Auto-Migration System** - Zero-downtime database schema updates
- ✅ **Error Sanitization** - Production-safe error messages
- ✅ **Connection Pooling** - Efficient resource management (Snowflake & SQLite)

### **Middleware Stack**

The server includes multiple middleware layers for security and reliability:

1. **TimeoutMiddleware** - Prevents hanging requests (5 min default, configurable)
2. **InputValidationMiddleware** - Validates request sizes, query lengths, file sizes
3. **RateLimitMiddleware** - Global and per-endpoint rate limiting
4. **CORSMiddleware** - Cross-origin resource sharing protection

---

## Architecture

```
unified-analytics-api/
├── main.py                      # Entrypoint (thin wrapper)
├── app/                         # App factory + wiring
├── routers/                     # Feature routers
│   ├── analytics_router.py      # Core analytics + PPT generation
│   ├── mcp_router.py            # MCP Protocol endpoints
│   ├── ml_router.py             # Machine learning
│   ├── transformation_router.py # Data quality
│   └── ...                      # 9 more routers
├── middleware/                  # Middleware components
│   ├── rate_limiter.py          # Rate limiting (global + per-endpoint)
│   └── input_validation.py     # Input validation
├── analysis/                    # Analysis modules
│   ├── roi/
│   ├── runrate/
│   ├── rca/
│   ├── capacity/
│   └── ...                      # 8 analysis modules
├── services/infrastructure/     # Infrastructure services
│   ├── jobs/                    # Job queue system
│   ├── ml/                      # Anomaly, forecast, predict
│   ├── transformation/          # Data cleaning, ETL
│   ├── backup/                  # Backup & recovery
│   ├── auth/                    # Authentication
│   ├── cache/                   # Redis + LRU cache
│   ├── snowflake/               # Connection pool
│   ├── scheduler/               # Background jobs
│   └── monitoring/              # Health & alerts
├── models/                      # Database models
│   ├── database.py              # SQLAlchemy setup + pooling
│   ├── migrations.py            # Auto-migrations
│   ├── scheduler.py             # Job schema
│   ├── monitoring.py            # Metrics schema
│   └── audit.py                 # Audit schema
├── utils/                       # Utilities
│   ├── error_handling.py        # Error sanitization
│   ├── standardized_errors.py   # Error decorators
│   ├── input_validation.py      # Input validation
│   └── sql_validation.py        # SQL injection prevention
└── tests/                       # 🧪 Test suite
    ├── test_job_queue.py        # Job queue tests
    ├── test_error_handling.py    # Error handling tests
    └── ...                      # Additional test files
```

**Key Design Principles:**
- **One server, one port**: no microservices complexity
- **Direct function calls**: no internal HTTP overhead
- **Auto-migrations**: database schema updates automatically on startup
- **Graceful fallbacks**: Redis unavailable → LRU cache; auth disabled → API still works
- **Async job processing**: long-running tasks don’t block API requests
- **Automatic cleanup**: jobs, logs, and connections are managed automatically

---

## 🔧 Configuration

### Environment Variables

Create `.env` file (see `COPY_TO_ENV.txt` for template):

#### **Server Configuration**
```bash
SERVER_PORT=3020
SERVER_HOST=0.0.0.0
ENVIRONMENT=production  # or development
```

#### **Snowflake (Required)**
```bash
SNOWFLAKE_USER=your_user
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema
SNOWFLAKE_PASSWORD=your_password
# or use private key
SNOWFLAKE_PRIVATE_KEY_PATH=path/to/key.p8
SNOWFLAKE_PRIVATE_KEY_PASSWORD=your_key_password

# Connection Pool Configuration
SNOWFLAKE_MAX_POOL_SIZE=10  # Maximum connections in pool (default: 10)
SNOWFLAKE_NETWORK_TIMEOUT=3600  # Network timeout in seconds (default: 3600)
SNOWFLAKE_LOGIN_TIMEOUT=60  # Login timeout in seconds (default: 60)
SNOWFLAKE_STATEMENT_TIMEOUT=7200  # Statement timeout in seconds (default: 7200)
SNOWFLAKE_OCSP_FAIL_OPEN=True  # Allow connection if OCSP fails (default: True)
```

#### **Security & Rate Limiting**
```bash
# CORS Configuration
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3020  # Comma-separated

# Rate Limiting
RATE_LIMIT_ENABLED=True  # Enable/disable rate limiting
RATE_LIMIT_DEFAULT=100/minute  # Global default rate limit

# Per-Endpoint Rate Limits (optional, overrides default)
RATE_LIMIT_ROI=20/minute
RATE_LIMIT_RUNRATE=20/minute
RATE_LIMIT_CAPACITY=20/minute
RATE_LIMIT_RCA=10/minute
RATE_LIMIT_DB_QUERY=30/minute
RATE_LIMIT_MCP_CALL=50/minute
RATE_LIMIT_PPT=5/minute
RATE_LIMIT_WEEKLY_PPT=3/minute

# Request Timeout
REQUEST_TIMEOUT_SECONDS=300.0  # 5 minutes default

# Input Validation
MAX_REQUEST_SIZE_BYTES=10485760  # 10 MB default
MAX_QUERY_LENGTH=10000  # 10,000 characters default
MAX_FILE_SIZE_BYTES=52428800  # 50 MB default
```

#### **Logging**
```bash
LOG_MAX_BYTES=10485760  # 10 MB per log file (default)
LOG_BACKUP_COUNT=5  # Number of backup files to keep (default: 5)
```

#### **Optional Services**
```bash
# Redis (for caching)
REDIS_HOST=localhost
REDIS_PORT=6379

# SMTP (for emails)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_password
ALERT_EMAIL=admin@company.com

# Feature Toggles
AUTH_ENABLED=False  # Set to True to enable JWT authentication
```

#### **Authentication (Optional)**
```bash
AUTH_ENABLED=True
JWT_SECRET_KEY=your-256-bit-secret-key-change-this
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 📚 API Documentation

### Interactive Docs

Visit http://localhost:3020/docs for full interactive API documentation with:
- All 100+ endpoints listed
- Request/response schemas
- Try-it-now functionality
- Authentication setup

### Key Endpoints

#### **Analytics**
```bash
# ROI Analysis
POST /analytics/roi
{
  "equipment_codes": ["EMA-4104"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "client": "VANTIS"
}

# RunRate Analysis
POST /analytics/runrate
{
  "equipment_codes": ["EMA-4102"],
  "start_date": "2024-11-21",
  "end_date": "2024-11-27",
  "supplier_names": ["VANTIS"]
}

# Generate PowerPoint
POST /analytics/generate_ppt
{
  "analysis_type": "runrate",
  "metrics": {...},
  "equipment_code": "EMA-4102",
  "supplier_name": "VANTIS",
  "start_date": "2024-11-21",
  "end_date": "2024-11-27"
}

# Weekly Comparison PowerPoint
POST /analytics/generate_weekly_comparison_ppt
{
  "equipment_code": "EMA-4102",
  "week1_start_date": "2024-11-14",
  "week1_end_date": "2024-11-20",
  "week2_start_date": "2024-11-21",
  "week2_end_date": "2024-11-27",
  "client": "VANTIS"
}
```

#### **Job Queue**
```bash
# Submit a job for async execution
POST /tools/submit
{
  "tool_name": "run_runrate_analysis",
  "arguments": {
    "equipment_codes": ["EMA-4102"],
    "start_date": "2024-11-21",
    "end_date": "2024-11-27"
  }
}

# Check job status
GET /tools/jobs/{job_id}

# List recent jobs
GET /tools/jobs?limit=50
```

#### **MCP Protocol**
```bash
# List available tools
POST /tools/list

# Call a tool via MCP
POST /tools/call
{
  "name": "run_runrate_analysis",
  "arguments": {...}
}

# Get MCP server info
GET /mcp/info
```

---

## 🧪 Testing

### Run Tests
```bash
# Install pytest
pip install pytest pytest-asyncio

# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_job_queue.py -v
pytest tests/test_error_handling.py -v
pytest tests/test_routers.py -v
```

### Test Coverage

Current test coverage includes:
- ✅ Job queue operations (submission, execution, cleanup)
- ✅ Error handling (sanitization, decorators)
- ✅ Database operations
- ✅ Email queue processing
- ✅ ML operations
- ✅ Data transformation
- ✅ Router endpoints

### Health Check
```bash
curl http://localhost:3020/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-28T10:00:00",
  "server": {
    "port": 3020,
    "environment": "production",
    "python_version": "3.10.0"
  },
  "checks": {
    "api": "ok",
    "job_queue": {
      "status": "ok",
      "size": 5,
      "jobs_by_status": {
        "pending": 1,
        "running": 2,
        "completed": 2,
        "failed": 0
      }
    }
  }
}
```

---

## 🔒 Security Configuration

### Production Security Checklist

Before deploying to production, ensure these security settings are configured:

#### 1. **CORS Protection**
```bash
# In .env - Configure allowed origins (comma-separated)
# Default: http://localhost:3000,http://localhost:3020 (for local development)
CORS_ALLOWED_ORIGINS=https://your-frontend.com,https://app.yourcompany.com
```

**Configuration Details:**
- **Default Origins**: `http://localhost:3000,http://localhost:3020` (local development)
- **Production**: Only specify your actual frontend domains (comma-separated)
- **Security**: Never use `*` in production! Only specified origins are allowed
- **Credentials**: Enabled for authenticated requests
- **Methods**: All HTTP methods allowed (GET, POST, PUT, DELETE, PATCH, OPTIONS)
- **Headers**: All headers allowed (configurable via middleware)

#### 2. **Rate Limiting**
```bash
# In .env
RATE_LIMIT_ENABLED=True
RATE_LIMIT_DEFAULT=100/minute  # Global default
```

**Per-Endpoint Limits:**
- Analytics endpoints: 20/minute (ROI, RunRate, Capacity)
- RCA: 10/minute
- Database queries: 30/minute
- MCP Protocol: 50/minute
- PPT generation: 5/minute
- Weekly comparison PPT: 3/minute

Rate limits can be specified as:
- `100/second` - 100 requests per second
- `100/minute` - 100 requests per minute (default)
- `1000/hour` - 1000 requests per hour
- `10000/day` - 10000 requests per day

#### 3. **Request Timeout**
```bash
REQUEST_TIMEOUT_SECONDS=300.0  # 5 minutes default
```

Prevents hanging requests from consuming server resources.

#### 4. **Input Validation**
```bash
MAX_REQUEST_SIZE_BYTES=10485760  # 10 MB default
MAX_QUERY_LENGTH=10000  # 10,000 characters default
MAX_FILE_SIZE_BYTES=52428800  # 50 MB default
```

Protects against oversized requests and query injection attempts.

#### 5. **Authentication (Optional)**
```bash
# In .env - Enable when ready
AUTH_ENABLED=True
JWT_SECRET_KEY=your-256-bit-secret-key-change-this
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Security Headers

The API automatically includes security headers:
- `X-RateLimit-Limit` - Total requests allowed
- `X-RateLimit-Remaining` - Remaining requests
- `X-RateLimit-Reset` - When limit resets (Unix timestamp)
- `X-RateLimit-Endpoint` - Per-endpoint limit (if applicable)
- `Retry-After` - Seconds to wait if rate limited (429 response)

### Rate Limiting Behavior

**Normal Request**:
```bash
curl -i http://localhost:3020/health

HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1700000000
```

**Rate Limited (429)**:
```bash
curl -i http://localhost:3020/api/endpoint

HTTP/1.1 429 Too Many Requests
Retry-After: 45
Content-Type: application/json

{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": "100 requests per 60 seconds",
    "retry_after": 45,
    "endpoint": "/api/endpoint"
  }
}
```

### Monitoring Security Events

Check logs for security events:
```bash
# View rate limit events
tail -f logs/manufacturing_api.log | grep "Rate limit"

# View authentication failures (if AUTH_ENABLED=True)
tail -f logs/manufacturing_api.log | grep "Auth failed"

# View input validation failures
tail -f logs/manufacturing_api.log | grep "validation"
```

---

## 🔄 Database Migrations

The system includes automatic database migrations that run on server startup.

### How It Works

1. **Schema Versioning** - Database tracks which migrations have been applied
2. **Auto-Apply** - New migrations run automatically on startup
3. **Idempotent** - Safe to run multiple times

### Adding New Migrations

Edit `models/migrations.py`:

```python
def get_migrations() -> List[Tuple[int, str, str]]:
    return [
        (1, "Add retry fields", "ALTER TABLE ..."),
        (2, "Your new migration", "ALTER TABLE ..."),  # Add here
    ]
```

Restart server → Migration applies automatically.

### Manual Migration (if needed)

```bash
# Backup first
cp data/manufacturing.db data/manufacturing.db.backup

# Run migration manually
sqlite3 data/manufacturing.db < your_migration.sql
```

---

## 📊 System Monitoring

### Built-in Monitoring

The system includes comprehensive monitoring:

- **Health Checks** - `/health` endpoint with job queue status
- **Metrics Collection** - CPU, memory, disk usage
- **Alert Rules** - Configurable thresholds
- **Alert Channels** - Email, Slack (when configured)
- **Job Queue Monitoring** - Track background job status

### View Metrics

```bash
curl http://localhost:3020/monitoring/metrics
```

### Configure Alerts

```bash
curl -X POST http://localhost:3020/monitoring/alert-rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High CPU Usage",
    "condition": "cpu_percent > 80",
    "severity": "warning",
    "enabled": true
  }'
```

---

## 🚀 Deployment

### Production Checklist

- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Configure Redis for caching
- [ ] Set up SMTP for email notifications
- [ ] Enable authentication (`AUTH_ENABLED=True`)
- [ ] Configure alert email (`ALERT_EMAIL`)
- [ ] Set strong JWT secret (`JWT_SECRET_KEY`)
- [ ] Use HTTPS (reverse proxy like nginx)
- [ ] Set CORS allowed origins (not `*`)
- [ ] Configure rate limits (global and per-endpoint)
- [ ] Set request timeout (`REQUEST_TIMEOUT_SECONDS`)
- [ ] Configure input validation limits
- [ ] Set log rotation limits (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`)
- [ ] Configure Snowflake connection pool (`SNOWFLAKE_MAX_POOL_SIZE`)
- [ ] Schedule regular backups
- [ ] Monitor logs (`logs/manufacturing_api.log`)

### Docker Deployment (Optional)

```bash
# Build image
docker build -t unified-analytics-api .

# Run container
docker run -p 3020:3020 \
  --env-file .env \
  unified-analytics-api
```

### Systemd Service (Linux)

```ini
[Unit]
Description=Unified Analytics API + MCP Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/unified-analytics-api
Environment="PATH=/opt/unified-analytics-api/venv/bin"
ExecStart=/opt/unified-analytics-api/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 🤝 Development

### Adding a New Router

1. **Create router file**:
```python
# routers/my_feature_router.py
from fastapi import APIRouter
router = APIRouter()

@router.post("/my-endpoint")
async def my_endpoint():
    return {"status": "success"}
```

2. **Register in main.py**:
```python
from routers.my_feature_router import router as my_router
app.include_router(my_router, prefix="/my-feature", tags=["MyFeature"])
```

3. **Test**: http://localhost:3020/docs

### Code Style

- Use type hints
- Add docstrings
- Handle errors gracefully (use `@handle_errors` decorator)
- Log important events
- Return consistent response format:
  ```json
  {
    "status": "success" | "error",
    "data": {...},
    "message": "Human-readable message"
  }
  ```

### Error Handling

Use standardized error handling:

```python
from utils.standardized_errors import handle_errors

@router.post("/endpoint")
@handle_errors(default_message="Operation failed")
async def my_endpoint():
    # Your code here
    return result
```

---

## 📈 Performance

### Caching

Query results are cached automatically when Redis is available:
- Cache TTL: 1 hour (configurable)
- Tag-based invalidation
- Automatic fallback to LRU cache

### Connection Pooling

**Snowflake Connections:**
- Pool size: 10 (configurable via `SNOWFLAKE_MAX_POOL_SIZE`)
- Automatic retry on failure
- Connection health checks
- Oldest unused connections cleaned up when pool is full

**SQLite Connections:**
- Pool size: 5 connections
- Max overflow: 10 connections
- Connection recycling: Every 1 hour
- Pre-ping enabled: Verifies connections before use

### Background Jobs

Long-running tasks execute in background:
- Email sending
- Report generation
- Scheduled analyses
- Metrics collection
- PowerPoint generation

Jobs are automatically cleaned up after 24 hours.

### Log Rotation

Logs are automatically rotated to prevent disk space issues:
- Max file size: 10 MB (configurable via `LOG_MAX_BYTES`)
- Backup files: 5 (configurable via `LOG_BACKUP_COUNT`)
- Automatic rotation when size limit reached
- Old backups automatically deleted

---

## 🐛 Troubleshooting

### Server won't start

```bash
# Check port availability
lsof -ti:3020

# Kill existing process
kill -9 $(lsof -ti:3020)

# Check logs
tail -f logs/manufacturing_api.log
```

### Database errors

```bash
# Check database exists
ls -lh data/manufacturing.db

# Reset database (deletes all data!)
rm data/manufacturing.db
python main.py  # Recreates with migrations
```

### Snowflake connection fails

```bash
# Test credentials
python -c "
from analysis.shared.connections import get_snowflake_connection_params
print(get_snowflake_connection_params())
"

# Check connection pool status
curl http://localhost:3020/health
```

### Redis unavailable

System automatically falls back to LRU cache. To use Redis:
```bash
# Install Redis
brew install redis  # macOS
apt-get install redis-server  # Linux

# Start Redis
redis-server
```

### Job Queue Issues

```bash
# Check job queue status
curl http://localhost:3020/health | jq '.checks.job_queue'

# List recent jobs
curl http://localhost:3020/tools/jobs

# Check specific job
curl http://localhost:3020/tools/jobs/{job_id}
```

### Rate Limit Issues

```bash
# Check rate limit headers
curl -i http://localhost:3020/your-endpoint

# View rate limit events in logs
tail -f logs/manufacturing_api.log | grep "Rate limit"
```

---

## 📝 License

Internal use only - Proprietary

---

## 👤 Maintainer

**Utku Gulbardak**  


For questions or issues:
- Check API docs: http://localhost:3020/docs
- Review logs: `logs/manufacturing_api.log`
- Check this README

---

## 📅 Changelog

### Version 2.0 (Current)
- ✅ Added PowerPoint generation (single analysis + weekly comparison)
- ✅ Implemented asynchronous job queue system
- ✅ Added request timeout middleware
- ✅ Added input validation middleware
- ✅ Implemented per-endpoint rate limiting
- ✅ Added log file rotation
- ✅ Enhanced health check with job queue status
- ✅ Added SQLite connection pooling
- ✅ Enhanced Snowflake connection pool with size limits
- ✅ Standardized error handling across all routers
- ✅ Added comprehensive test coverage
- ✅ Improved documentation

---

**Last Updated**: November 28, 2025  
**System Status**: Production Ready

