@echo off
REM =====================================================================
REM  Daily auto update for Task Scheduler (non-interactive, no pause)
REM  Flow: build_cache.py (incremental raw data + refresh scores)
REM        -> deploy_scores.py (sync snapshot -> commit -> push)
REM  Logs: outputs\logs\daily_update_YYYYMMDD.log (kept 30 days)
REM  Manual run is fine too; it just won't wait for a keypress.
REM =====================================================================
setlocal
cd /d "%~dp0.."

REM Python prints emoji/Chinese; default cp950 console codec crashes on them
REM when stdout is redirected to a log file. Force UTF-8.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "LOGDIR=outputs\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TS=%%i"
set "LOG=%LOGDIR%\daily_update_%TS%.log"

echo ==== daily_auto_update start %date% %time% ==== >> "%LOG%"

REM prefer python, fall back to py launcher
set "PY=python"
where python >nul 2>nul || set "PY=py"

REM 1) incremental raw data + refresh today's scores (uses API quota)
"%PY%" build_cache.py >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] build_cache.py failed, skip deploy to keep last good snapshot. >> "%LOG%"
    echo ==== end with error %date% %time% ==== >> "%LOG%"
    exit /b 1
)

REM 2) sync scores snapshot -> commit -> push (no-op if scores unchanged)
"%PY%" deploy_scores.py --message "chore: daily auto update scores snapshot" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] deploy_scores.py failed - check git remote / network. >> "%LOG%"
    echo ==== end with error %date% %time% ==== >> "%LOG%"
    exit /b 1
)

REM 3) prune logs older than 30 days (best effort)
forfiles /P "%LOGDIR%" /M daily_update_*.log /D -30 /C "cmd /c del @path" >nul 2>nul

echo ==== daily_auto_update done %date% %time% ==== >> "%LOG%"
exit /b 0
