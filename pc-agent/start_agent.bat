@echo off
rem Spusti FramePulse agenta bez konzoloveho okna.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0start_agent.pyw"
    exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0start_agent.pyw"
    exit /b 0
)

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0start_agent.pyw"
    exit /b 0
)

echo Nebyl nalezen Python s pythonw.exe.
echo Spustte nejprve setup.bat.
pause
exit /b 1
