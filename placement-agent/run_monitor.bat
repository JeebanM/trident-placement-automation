@echo off
cd /d E:\tridentauto\placement-agent

if not exist logs mkdir logs

.venv\Scripts\python.exe run_monitor.py >> logs\monitor.log 2>&1

echo [%date% %time%] Exit code: %ERRORLEVEL% >> logs\monitor.log
