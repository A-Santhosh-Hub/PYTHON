@echo off
REM Edit the line below to the folder you want to share, then double-click this file.
REM Add a password by adding  --password yourpin  at the end if you're on a shared/office Wi-Fi.

set FOLDER=D:\Games

python server.py --folder "%FOLDER%" --port 5000

pause
