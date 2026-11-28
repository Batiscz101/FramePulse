@echo off

setlocal

cd /d "%~dp0m"

echo [1/2] Kontrola TypeScriptu...

call npx.cmd tsc --noEmit

if errorlevel 1 (

  echo CHYBA: TypeScript nasel chyby, build se rusi.

  pause

  exit /b 1

)

echo [2/2] Sestavovani FramePulse-v1.2.0.apk pres EAS Build...

call npx.cmd --yes eas-cli build -p android --profile preview --non-interactive --wait

if errorlevel 1 (

  echo CHYBA: Build APK selhal.

  pause

  exit /b 1

)

echo.

echo HOTOVO: Stahni APK z odkazu nebo QR kodu vyse a prejmenuj na FramePulse-v1.2.0.apk

pause

