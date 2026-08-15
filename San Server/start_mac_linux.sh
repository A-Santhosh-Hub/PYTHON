#!/usr/bin/env bash
# Edit FOLDER below to the folder you want to share, then run:  ./start_mac_linux.sh
# Add a password by adding  --password yourpin  at the end if you're on a shared/office Wi-Fi.

FOLDER="$HOME/Games"

python3 server.py --folder "$FOLDER" --port 5000
