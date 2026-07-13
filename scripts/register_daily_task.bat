@echo off
REM Double-click to register the daily auto-update scheduled task (Mon-Fri 20:30).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_daily_task.ps1"
echo.
pause
