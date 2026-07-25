@echo off
chcp 65001 >nul
title Исправить позывной в игре
:: --- самоповышение прав (файлы игры в Program Files) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Запрашиваю права администратора...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "CALLSIGN=7-WILLIAM-24"
set "BASE=C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR"

echo ============================================
echo   Устанавливаю позывной: %CALLSIGN%
echo ============================================
echo.

powershell -NoProfile -Command ^
  "$cs='%CALLSIGN%'; $base='%BASE%';" ^
  "$t=@(@{p=\"$base\GrammarPolice\custom.ini\";k='Callsign'},@{p=\"$base\CalloutInterface.ini\";k='MDTCallsign'},@{p=\"$base\BlueLineScanner.ini\";k='VizLabel'},@{p=\"$base\pdComp\config.ini\";k='Callsign'});" ^
  "foreach($i in $t){ if(Test-Path $i.p){ try{ $c=Get-Content $i.p -Raw -Encoding UTF8; $n=[regex]::Replace($c,\"(?m)^(\s*$($i.k)\s*=\s*).*$\",\"`${1}$cs\"); [System.IO.File]::WriteAllText($i.p,$n,[System.Text.UTF8Encoding]::new($false)); Write-Host ('  OK  '+(Split-Path $i.p -Leaf)) } catch { Write-Host ('  ОШИБКА '+(Split-Path $i.p -Leaf)+': '+$_.Exception.Message) } } }"

echo.
echo Готово. Позывной прописан во все файлы.
echo ВАЖНО: после обновления сборки Vinewood запусти этот файл снова —
echo обновление сбрасывает позывной на стандартный.
echo.
pause
