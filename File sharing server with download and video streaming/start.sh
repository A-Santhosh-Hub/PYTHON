#!/usr/bin/env bash
echo "============================================"
echo "  SanStudio File Server  —  Starting..."
echo "============================================"

pip install -r requirements.txt -q
python server.py
