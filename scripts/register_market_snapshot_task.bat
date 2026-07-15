@echo off
REM One-time registration of the Market_SnapshotCollector scheduled task.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_market_snapshot_task.ps1"
pause
