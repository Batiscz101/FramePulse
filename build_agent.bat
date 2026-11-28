@echo off
setlocal

echo === Aktualizace FramePulseAgent.exe ===
taskkill /F /IM FramePulseAgent.exe >nul 2>&1
call C:\f\pc-agent\build_exe.bat
copy /Y C:\f\pc-agent\dist\FramePulseAgent.exe C:\FramePulse\FramePulseAgent.exe
start "" "C:\FramePulse\FramePulseAgent.exe"

echo.
echo HOTOVO! Novy FramePulseAgent.exe uz bezi v liste.
pause
