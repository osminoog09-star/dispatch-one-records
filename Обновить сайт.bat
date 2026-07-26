@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Dispatch One - update site
echo ============================================
echo   LAPD Records - update site
echo   https://osminoog09-star.github.io/dispatch-one-records/
echo ============================================
echo.
py publish.py
echo.
pause
