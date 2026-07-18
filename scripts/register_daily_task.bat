@echo off
REM Double-click to register the daily auto-update scheduled task (Mon-Fri 18:00).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_daily_task.ps1"
echo.
pause
