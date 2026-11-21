@echo off
rem Builds a clean single-file FramePulseAgent.exe (no console) into dist\.
rem The executable bundles PresentMon and config.example.json, so dist\ contains
rem only FramePulseAgent.exe. Requires setup.bat to have created .venv.
setlocal EnableExtensions
set "PC=%~dp0"
cd /d "%PC%"

set "PY=%PC%.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: virtual environment not found: %PY%
    echo Run setup.bat first.
    exit /b 1
)

"%PY%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller into the virtual environment...
    "%PY%" -m pip install --upgrade pyinstaller
    if errorlevel 1 goto :error
)

if not exist "tools\PresentMon.exe" (
    echo PresentMon not found, downloading it first...
    "%PY%" download_presentmon.py
    if errorlevel 1 goto :error
)

if not exist "assets\framepulse.ico" (
    echo Generating the application icon...
    "%PY%" "assets\make_icon.py"
    if errorlevel 1 goto :error
)

echo Cleaning previous build output...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo Building FramePulseAgent.exe ...
"%PY%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --noconsole ^
    --name FramePulseAgent ^
    --icon "%PC%assets\framepulse.ico" ^
    --add-binary "%PC%tools\PresentMon.exe;tools" ^
    --add-data "%PC%config.example.json;." ^
    --hidden-import pystray._win32 ^
    "%PC%framepulse_agent\__main__.py"
if errorlevel 1 goto :error

if not exist "dist\FramePulseAgent.exe" goto :error

for %%F in ("dist\FramePulseAgent.exe") do set "EXE_SIZE=%%~zF"
echo.
echo Done: %PC%dist\FramePulseAgent.exe (%EXE_SIZE% bytes)
echo Run it directly - the tray agent starts without a console.
exit /b 0

:error
echo.
echo ERROR: build failed.
exit /b 1
