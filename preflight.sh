#!/bin/bash

# Manufacturing Analytics API - Dependency Preflight.
# Sourced by start_server.sh and restart_server.sh before the server boots.
# Verifies the chosen Python interpreter has the core requirements so a partial
# environment fails loudly here instead of silently disabling routers at runtime.

# Interpreter is overridable: PYTHON=/opt/anaconda3/bin/python ./start_server.sh
PYTHON="${PYTHON:-python}"

# Core modules: absence disables whole router groups or breaks startup.
REQUIRED_MODULES="fastapi uvicorn pandas sqlalchemy snowflake.snowpark"
# Optional modules: each disables a single feature; warn but continue.
OPTIONAL_MODULES="sentence_transformers email_validator pptx redis"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: Python interpreter '$PYTHON' not found on PATH."
    echo "       Set PYTHON to a valid interpreter, e.g.:"
    echo "       PYTHON=/opt/anaconda3/bin/python ./start_server.sh"
    exit 1
fi

echo "Using interpreter: $("$PYTHON" -c 'import sys; print(sys.executable)')"

missing_required=""
for module in $REQUIRED_MODULES; do
    if ! "$PYTHON" -c "import $module" >/dev/null 2>&1; then
        missing_required="$missing_required $module"
    fi
done

if [ -n "$missing_required" ]; then
    echo "ERROR: this environment is missing required packages:$missing_required"
    echo "       Install them with:"
    echo "       $PYTHON -m pip install -r requirements.txt"
    echo "       Or launch with a provisioned interpreter:"
    echo "       PYTHON=/opt/anaconda3/bin/python ./start_server.sh"
    exit 1
fi

missing_optional=""
for module in $OPTIONAL_MODULES; do
    if ! "$PYTHON" -c "import $module" >/dev/null 2>&1; then
        missing_optional="$missing_optional $module"
    fi
done

if [ -n "$missing_optional" ]; then
    echo "WARNING: optional packages missing, related features stay disabled:$missing_optional"
    echo "         Run '$PYTHON -m pip install -r requirements.txt' to enable them. Continuing."
fi
