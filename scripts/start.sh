#!/bin/bash

###############################################################################
# Manufacturing Analytics - Unified API Starter
#
# Single server, single port, single command to start everything.
# No microservices complexity, no port conflicts.
#
# Author: Utku Gulbardak
# Date: 2025-11-24
###############################################################################

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_DIR="/Users/utkugulbardak/Desktop/cotexai/manufacturing-api"
PORT=3020

echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║     Manufacturing Analytics - Unified API Starter          ║${NC}"
echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python found: $(python --version)${NC}"

# Check if port is already in use
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠️  Port $PORT is already in use${NC}"
    echo -e "${YELLOW}   Killing existing process...${NC}"
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Create logs directory
mkdir -p logs

# Start server
cd $PROJECT_DIR
echo -e "${BLUE}🚀 Starting Manufacturing Analytics API...${NC}"
python main.py &
SERVER_PID=$!

# Wait for server to start
sleep 5

# Check if server is running
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo ""
    echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║                    ✅ SERVER RUNNING!                       ║${NC}"
    echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}📊 API Information:${NC}"
    echo -e "   Server: ${GREEN}http://localhost:$PORT${NC}"
    echo -e "   Docs: ${YELLOW}http://localhost:$PORT/docs${NC}"
    echo -e "   Health: ${YELLOW}http://localhost:$PORT/health${NC}"
    echo ""
    echo -e "${CYAN}🔧 Quick Commands:${NC}"
    echo -e "   Test health: ${YELLOW}curl http://localhost:$PORT/health${NC}"
    echo -e "   View API docs: ${YELLOW}open http://localhost:$PORT/docs${NC}"
    echo -e "   Stop server: ${YELLOW}./scripts/stop.sh${NC}"
    echo ""
    echo -e "${CYAN}📋 Logs:${NC}"
    echo -e "   ${YELLOW}tail -f logs/manufacturing_api.log${NC}"
    echo ""
else
    echo -e "${RED}❌ Failed to start server${NC}"
    echo -e "${YELLOW}Check logs: tail -f logs/manufacturing_api.log${NC}"
    exit 1
fi

