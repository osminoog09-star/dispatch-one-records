@echo off
title Dispatch One + Vinewood
cd /d "%~dp0"

set "AGENT=%~dp0..\agent\pdcomp_sync.py"
set "VINEWOOD=C:\Program Files\Vinewood Launcher\Vinewood Launcher.exe"

echo ============================================
echo   LAPD Records - start
echo ============================================
echo.

echo [1/2] Sync agent...
if exist "%~dp0..\agent\dist\pdcomp_sync.exe" (
    start "" /min "%~dp0..\agent\dist\pdcomp_sync.exe"
) else (
    start "Dispatch One sync" /min cmd /c "py "%AGENT%""
)
echo       started (works in background, syncs while you play)

echo [2/2] Vinewood Launcher...
if exist "%VINEWOOD%" (
    start "" "%VINEWOOD%"
    echo       started
) else (
    echo       NOT FOUND: %VINEWOOD%
    echo       Edit this file and set the correct path.
)

echo.
echo Done. You can close this window.
timeout /t 4 >nul
