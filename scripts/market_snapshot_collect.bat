@echo off
REM =====================================================================
REM  TWSE/TPEx market snapshot collector + L1/L2 universe screen
REM  (0 FinMind API - official open data only; see DevLog section 15)
REM  Flow: market_snapshot_collector.py (fetch & store today's snapshot)
REM        -> universe_screen_daily.py (L0/L1/L2 -> outputs\universe_pool\)
REM  Logs: outputs\logs\market_snapshot_YYYYMMDD.log
REM  Idempotent: holiday / re-run = no-op (endpoints serve latest trade day)
REM =====================================================================
setlocal
cd /d "%~dp0.."

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "LOGDIR=outputs\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TS=%%i"
set "LOG=%LOGDIR%\market_snapshot_%TS%.log"

echo ==== market_snapshot_collect start %date% %time% ==== >> "%LOG%"

set "PY=python"
where python >nul 2>nul || set "PY=py"

"%PY%" scripts\market_snapshot_collector.py >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] collector failed, skip screening >> "%LOG%"
    exit /b 1
)

"%PY%" scripts\universe_screen_daily.py >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] universe screen failed >> "%LOG%"
    exit /b 1
)

echo ==== market_snapshot_collect done %date% %time% ==== >> "%LOG%"
endlocal
