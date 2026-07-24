@echo off
chcp 65001 >nul
cd /d "%~dp0\..\server"
title Dispatch One - САЙТ (не закрывать)
echo ============================================
echo   Dispatch One - сайт
echo   Открой в браузере: http://localhost:8000
echo   Не закрывай это окно.
echo ============================================
echo.

REM Настройки сообщества (поменяй ключ на секретный, когда пойдут другие):
set RECORDS_API_KEY=dev-key
set COMMUNITY_NAME=LAPD
set OFFICER_NAME=Denis Sherman

py run.py
echo.
echo Сайт остановлен.
pause
