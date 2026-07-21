#!/bin/bash

# Manufacturing Analytics API - Server Restart Script
# This script kills any existing server process and starts a fresh one

set -e

PORT=3020
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔄 Restarting Manufacturing Analytics API..."

# Find and kill any process using port 3020
PID=$(lsof -ti:$PORT 2>/dev/null || true)

if [ -n "$PID" ]; then
    echo "🛑 Stopping existing server (PID: $PID)..."
    kill -9 $PID 2>/dev/null || true
    sleep 2
    echo "✅ Server stopped"
else
    echo "ℹ️  No existing server found on port $PORT"
fi

# Wait a moment to ensure port is free
sleep 1

# Check if port is still in use
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "⚠️  Warning: Port $PORT is still in use. Trying force kill..."
    kill -9 $(lsof -ti:$PORT) 2>/dev/null || true
    sleep 2
fi

# Verify the interpreter has the required dependencies before booting
source "$SCRIPT_DIR/preflight.sh"

# Start the server
echo "🚀 Starting server..."
cd "$SCRIPT_DIR"
"$PYTHON" main.py

