@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Dispatch One - обновление сайта
echo ============================================
echo   Обновление публичного сайта
echo   https://osminoog09-star.github.io/dispatch-one-records/
echo ============================================
echo.
py publish.py
echo.
pause
