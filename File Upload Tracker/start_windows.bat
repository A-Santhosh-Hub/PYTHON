@echo off
title DropStream Upload Server
color 0A

echo.
echo  ============================================
echo   DropStream - Fast File Upload Server
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Install deps if needed
echo  [1/3] Installing dependencies...
pip install -r requirements.txt -q

:: Check cloudflared
echo  [2/3] Checking Cloudflare Tunnel...
where cloudflared >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [INFO] cloudflared not found.
    echo  Download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    echo  Place cloudflared.exe in this folder, then restart.
    echo.
    echo  Continuing with LOCAL access only (http://localhost:8000)
    echo.
    start "" python server.py
) else (
    echo  [3/3] Starting Cloudflare Tunnel on port 8000...
    start "" python server.py
    timeout /t 2 /nobreak >nul
    cloudflared tunnel --url http://localhost:8000
)

echo.
echo  Server stopped.
pause
