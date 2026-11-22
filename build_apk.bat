@echo off
setlocal

:: 1. Nastaveni verze (uprav podle aktualni verze)
set "VER=1.1.0"

:: 2. Nastaveni Java JDK 17 a Android SDK
for /d %%i in ("C:\Program Files\Eclipse Adoptium\jdk-17*") do set "JAVA_HOME=%%i"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "PATH=%JAVA_HOME%\bin;%ANDROID_HOME%\platform-tools;%PATH%"

:: 3. Zkraceni cesty kvuli limitu 260 znaku ve Windows (CMake/Ninja)
cd /d C:\f
if exist C:\f\mobile-app ren C:\f\mobile-app m
cd /d C:\f\m

:: 4. Vygenerovani Android projektu s klici z .env.local
call npx expo prebuild --platform android --clean

:: 5. Presmerovani CMake mezipameti do kratke slozky C:\x
powershell -Command "(Get-Content C:\f\m\android\app\build.gradle) -replace '^android \{', 'android { externalNativeBuild { cmake { buildStagingDirectory file(\"C:/x\") } }' | Set-Content C:\f\m\android\app\build.gradle"

:: 6. Kompilace release APK
cd /d C:\f\m\android
call gradlew.bat assembleRelease
call gradlew.bat --stop

:: 7. Vyzvednuti hotoveho APK a uklid
mkdir C:\f\m\dist >nul 2>&1
copy /Y C:\f\m\android\app\build\outputs\apk\release\app-release.apk C:\f\m\dist\FramePulse-v%VER%.apk
copy /Y C:\f\m\android\app\build\outputs\apk\release\app-release.apk "%USERPROFILE%\Desktop\FramePulse-v%VER%.apk"

cd /d C:\f
rmdir /s /q C:\x >nul 2>&1
if exist C:\f\m ren C:\f\m mobile-app

echo.
echo HOTOVO! Soubor FramePulse-v%VER%.apk je na plose i v C:\f\mobile-app\dist\
pause
