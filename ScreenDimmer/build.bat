@echo off
setlocal
cd /d "%~dp0"

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo Could not find the C# compiler at:
    echo %CSC%
    exit /b 1
)

"%CSC%" /nologo /target:winexe /platform:x64 /optimize+ ^
    /out:ScreenDimmer.exe ^
    /reference:System.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll ^
    src\ScreenDimmer.cs
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo Built ScreenDimmer.exe
