@echo off
chcp 65001 >nul
title Dispatch One - fix callsign
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel%==0 goto :run

echo Запрашиваю права администратора...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c','\"%~f0\"' -Verb RunAs"
exit /b

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix-callsign.ps1"
