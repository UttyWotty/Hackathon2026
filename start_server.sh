#!/bin/bash

# Manufacturing Analytics API - Server Start Script
# This script starts the server (will fail if port is already in use)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Manufacturing Analytics API..."

# Check if port is already in use
PORT=3020
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "❌ Error: Port $PORT is already in use!"
    echo "   Use './restart_server.sh' to restart, or './stop_server.sh' to stop first"
    exit 1
fi

# Verify the interpreter has the required dependencies before booting
source "$SCRIPT_DIR/preflight.sh"

# Start the server
cd "$SCRIPT_DIR"
"$PYTHON" main.py

