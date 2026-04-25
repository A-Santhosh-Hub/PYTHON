@echo off
title SanStudio File Server
echo.
echo  ============================================
echo    SanStudio File Server  -  Starting...
echo  ============================================
echo.

REM Install dependencies if needed
pip install -r requirements.txt --quiet

echo  Server running at  http://localhost:5000
echo  Press Ctrl+C to stop.
echo.
python server.py
pause
