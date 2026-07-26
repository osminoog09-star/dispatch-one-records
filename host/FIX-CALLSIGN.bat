@echo off
title Dispatch One - fix callsign
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel%==0 goto :run

echo Requesting administrator rights...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c','\"%~f0\"' -Verb RunAs"
exit /b

:run
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix-callsign.ps1"
