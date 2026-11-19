@echo off
setlocal
cd /d "%~dp0"
if exist "C:\Python313\pythonw.exe" (
    start "" "C:\Python313\pythonw.exe" "%~dp0student_agent.py"
) else (
    start "" pythonw "%~dp0student_agent.py"
)
exit
