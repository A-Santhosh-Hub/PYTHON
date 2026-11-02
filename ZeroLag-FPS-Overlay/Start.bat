@echo off
rem Double-click to start the FPS overlay. Keep this file in the same folder as FpsOverlay.ps1.
cd /d "%~dp0"
start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0FpsOverlay.ps1"
