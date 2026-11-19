@echo off
rem Jednorazova priprava: virtualni prostredi, zavislosti, PresentMon.
setlocal
cd /d "%~dp0"

set "PY=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY=python"

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo Python 3 nebyl nalezen. Nainstalujte Python 3.10+ z python.org
    echo a pri instalaci zaskrtnete "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Vytvarim virtualni prostredi .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto error
)

set "VENV_PY=.venv\Scripts\python.exe"

"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto error

"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto error

"%VENV_PY%" download_presentmon.py
if errorlevel 1 goto error

if not exist "config.json" (
    copy /y "config.example.json" "config.json" >nul
    echo Vytvoren config.json s ukazkovymi hodnotami.
    echo Pred spustenim v nem vyplnte supabase_url a supabase_key.
)

echo.
echo Hotovo. Agent spustite souborem start_agent.bat.
echo Po spusteni najdete ikonu pulzu v oznamovaci oblasti vedle hodin.
echo.
echo Pro automaticke spusteni po prihlaseni:
echo     .venv\Scripts\python.exe autostart.py enable
echo.
pause
exit /b 0

:error
echo.
echo Instalace selhala. Zkontrolujte pripojeni k internetu a zkuste to znovu.
pause
exit /b 1
