@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Dispatch One - публичный доступ (не закрывать)
echo ============================================
echo   Публичный доступ к сайту
echo ============================================
echo   Ниже появится адрес вида:
echo     https://XXXX.trycloudflare.com
echo   Скопируй его и дай другим игрокам.
echo   Держи это окно открытым, пока хочешь,
echo   чтобы сайт был доступен другим.
echo ============================================
echo.
echo   ВАЖНО: сначала запусти "1. Запустить САЙТ.bat"
echo.
cloudflared.exe tunnel --url http://localhost:8000 --no-autoupdate
echo.
echo Публичный доступ остановлен.
pause
