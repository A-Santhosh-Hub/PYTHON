@echo off
echo Installing requirements...
pip install pyinstaller pillow
echo Building EXE...
pyinstaller --noconsole --onefile --name SanGameLauncher SanGameLauncher.py
echo.
echo Done! Your app is in the "dist" folder: dist\SanGameLauncher.exe
pause
