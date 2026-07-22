@echo off
REM =====================================================================
REM  Daily auto update for Task Scheduler (non-interactive, no pause)
REM  Flow: build_cache.py --build-scores --source tej --universe-from <latest pool>
REM          (5-dim composite for the ~900-stock L1 pool from LOCAL TEJ cache,
REM           0 FinMind API; pool_{date}.csv is produced by Market_Snapshot-
REM           Collector at 17:30, so it exists by this task's 18:00 run)
REM        -> deploy_scores.py (sync snapshot -> commit -> push)
REM  2026-07-21: switched from "build_cache.py (no args = watchlist + FinMind
REM   incremental)" to pool + TEJ. The whole daily pipeline is now 0 FinMind
REM   API (collector = official open data; scores = local TEJ). The 綜合分頁
REM   universe is now the daily L1 pool (~900), not the 45-stock watchlist.
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

REM 1) build 5-dim scores for the daily L1 pool from LOCAL TEJ cache (0 FinMind API).
REM    pool_{date}.csv is written by Market_SnapshotCollector (17:30) before this run.
set "POOL="
for /f "delims=" %%f in ('powershell -NoProfile -Command "$p=Get-ChildItem 'outputs\universe_pool\pool_*.csv' -ErrorAction SilentlyContinue ^| Sort-Object Name ^| Select-Object -Last 1; if ($p) { $p.FullName }"') do set "POOL=%%f"
if not defined POOL (
    echo [ERROR] no outputs\universe_pool\pool_*.csv found -- did Market_SnapshotCollector run at 17:30? >> "%LOG%"
    echo ==== end with error %date% %time% ==== >> "%LOG%"
    exit /b 1
)
echo [info] building scores from pool: %POOL% >> "%LOG%"
"%PY%" build_cache.py --build-scores --source tej --universe-from "%POOL%" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] build-scores (tej/pool) failed, skip deploy to keep last good snapshot. >> "%LOG%"
    echo ==== end with error %date% %time% ==== >> "%LOG%"
    exit /b 1
)

REM 1b) refresh 市場燈號 regime exposure snapshot -> cloud_cache (best effort, non-fatal).
REM      deploy_scores.py does `git add cloud_cache`, so this snapshot ships to cloud too.
"%PY%" -m core.regime_exposure >> "%LOG%" 2>&1
if errorlevel 1 echo [warn] regime_exposure snapshot refresh failed, keeping last snapshot. >> "%LOG%"

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
