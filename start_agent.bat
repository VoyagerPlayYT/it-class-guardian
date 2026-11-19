@echo off
chcp 65001 > nul
title IT-Class Guardian // Станция Ученика (Агент)
echo ========================================================
echo   IT-CLASS GUARDIAN // СТАНЦИЯ УЧЕНИКА
echo ========================================================

if exist "C:\Python313\python.exe" (
    set "PY=C:\Python313\python.exe"
) else (
    set "PY=python"
)

echo [INFO] Запуск фонового агента ученика...
cd /d "%~dp0"
"%PY%" student_agent.py
pause
