#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "  ============================================"
echo "   DropStream — Fast File Upload Server"
echo "  ============================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[ERROR]${NC} Python 3 not found."
    exit 1
fi

# Install deps
echo -e "${GREEN}[1/3]${NC} Installing Python dependencies..."
pip3 install -r requirements.txt -q

echo -e "${GREEN}[2/3]${NC} Starting upload server on :8000..."
python3 server.py &
SERVER_PID=$!
sleep 2

# Try cloudflared
if command -v cloudflared &>/dev/null; then
    echo -e "${GREEN}[3/3]${NC} Opening Cloudflare Tunnel..."
    echo -e "${YELLOW}     Copy the https://xxxxx.trycloudflare.com URL and share it!${NC}"
    echo ""
    cloudflared tunnel --url http://localhost:8000
else
    echo ""
    echo -e "${YELLOW}[INFO]${NC} cloudflared not found."
    echo "       Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    echo ""
    echo -e "${GREEN}       Local URL: http://localhost:8000${NC}"
    echo "       Press Ctrl+C to stop."
    wait $SERVER_PID
fi

# Cleanup
kill $SERVER_PID 2>/dev/null || true
