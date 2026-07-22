@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Сборка standalone .exe для раздачи игрокам...
py -m pip install pyinstaller
py -m PyInstaller --onefile --name pdcomp_sync --distpath dist --workpath build --specpath build pdcomp_sync.py
copy /Y sync-config.ini dist\sync-config.ini
echo.
echo Готово. Раздавай папку "dist" целиком:
echo   dist\pdcomp_sync.exe
echo   dist\sync-config.ini
echo   dist\Запустить синхронизацию.bat
echo   dist\ЧИТАЙ МЕНЯ.txt
pause
