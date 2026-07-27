#!/bin/bash

# Cortex Workflow Agent - Demo UI Start Script.
# Launches the Streamlit demo on port 8501, after the same interpreter
# preflight the API server uses. The demo triggers real agent runs, so a
# partial environment must fail here rather than halfway through a run.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DEMO_PORT="${DEMO_PORT:-8501}"

echo "Starting the autonomous agent demo..."

if lsof -ti:"$DEMO_PORT" >/dev/null 2>&1; then
    echo "ERROR: port $DEMO_PORT is already in use."
    echo "       Stop the process using it, or set DEMO_PORT to another port."
    exit 1
fi

source "$SCRIPT_DIR/preflight.sh"

if ! "$PYTHON" -c "import streamlit" >/dev/null 2>&1; then
    echo "ERROR: streamlit is not installed in this interpreter."
    echo "       $PYTHON -m pip install -r requirements.txt"
    exit 1
fi

# The demo grades runs against the generator's ground_truth.json, which only
# exists beside a generated dataset. Without it the app still runs, but the
# score card and the drift chart are unavailable, so say so up front.
if [ -z "$LOCAL_DATA_DIR" ]; then
    echo "NOTE: LOCAL_DATA_DIR is unset, so the demo will query Snowflake and"
    echo "      cannot grade runs. For the offline demo, run:"
    echo "      LOCAL_DATA_DIR=./synthetic_out ./start_demo.sh"
fi

cd "$SCRIPT_DIR"
"$PYTHON" -m streamlit run demo/app.py --server.port "$DEMO_PORT"
