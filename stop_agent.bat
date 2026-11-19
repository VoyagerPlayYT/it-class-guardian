@echo off
setlocal
taskkill /f /im Агент_Ученика.exe >nul 2>&1
wmic process where "commandline like '%%student_agent.py%%'" call terminate >nul 2>&1
echo [OK] Фоновый агент ученика остановлен.
timeout /t 2 >nul
