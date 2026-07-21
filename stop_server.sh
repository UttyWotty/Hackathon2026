#!/bin/bash

# Manufacturing Analytics API - Server Stop Script
# This script stops the server running on port 3020

set -e

PORT=3020

echo "🛑 Stopping Manufacturing Analytics API..."

# Find and kill any process using port 3020
PID=$(lsof -ti:$PORT 2>/dev/null || true)

if [ -n "$PID" ]; then
    echo "Stopping server (PID: $PID)..."
    kill -9 $PID 2>/dev/null || true
    sleep 1
    echo "✅ Server stopped"
else
    echo "ℹ️  No server found running on port $PORT"
fi

