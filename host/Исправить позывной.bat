@echo off
chcp 65001 >nul
title Исправить позывной в игре
cd /d "%~dp0"
echo Запускаю с правами администратора (файлы игры в Program Files)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0fix-callsign.ps1\"' -Verb RunAs"
exit /b
