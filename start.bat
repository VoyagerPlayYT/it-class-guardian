@echo off
chcp 65001 > nul
title IT-Class Guardian // Teacher Server [Port 8023]
echo ========================================================
echo   IT-CLASS GUARDIAN // ПАНЕЛЬ УЧИТЕЛЯ И СЕРВЕР КЛАССА
echo ========================================================

if exist "C:\Python313\python.exe" (
    set "PY=C:\Python313\python.exe"
) else (
    set "PY=python"
)

echo [INFO] Проверка и освобождение порта 8023...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8023" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [INFO] Запуск веб-сервера на http://localhost:8023 ...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8023"

cd /d "%~dp0"
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8023
pause
