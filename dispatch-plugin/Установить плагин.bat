@echo off
chcp 65001 >nul
title Установка плагина DispatchOne.MDT
rem --- самоповышение до администратора (один клик "Да") ---
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Запрашиваю права администратора...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "SRC=%~dp0out\DispatchOne.MDT.dll"
set "G1=C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR"
set "G2=C:\Program Files\Rockstar Games\Grand Theft Auto V\plugins\LSPDFR"

set "DST="
if exist "%G1%" set "DST=%G1%"
if not defined DST if exist "%G2%" set "DST=%G2%"

if not defined DST (
  echo [ОШИБКА] Не нашёл папку plugins\LSPDFR. Установлен ли LSPDFR?
  pause
  exit /b 1
)

echo Копирую плагин в:
echo   %DST%
copy /Y "%SRC%" "%DST%\DispatchOne.MDT.dll" >nul
if %errorlevel% equ 0 (
  echo.
  echo [ГОТОВО] Плагин установлен.
  echo Теперь запусти игру через RagePluginHook, встань на смену,
  echo пробей одного NPC и один номер машины. Потом запусти "Проверить плагин.bat".
) else (
  echo [ОШИБКА] Не удалось скопировать. Закрой игру и попробуй снова.
)
echo.
pause
