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

REM 2026-07-23: step markers also go to a SECOND log, on a local disk OUTSIDE
REM OneDrive. Why: on 7/22 and 7/23 this task died mid-run with exit 255 and
REM left no trace -- cmd simply stopped executing the next line, so none of the
REM error branches below ever wrote anything. One suspect we could not rule out
REM is OneDrive locking %LOG% (the whole project lives under OneDrive), which
REM would make a failure invisible. %MARK% is unaffected by OneDrive, so if the
REM two logs ever disagree we have our answer.
set "MARKDIR=%LOCALAPPDATA%\FinMind"
if not exist "%MARKDIR%" mkdir "%MARKDIR%"
set "MARK=%MARKDIR%\daily_update_%TS%.marker.log"

call :mark "==== daily_auto_update start ===="

REM prefer python, fall back to py launcher
set "PY=python"
where python >nul 2>nul || set "PY=py"

REM 1) build 5-dim scores for the daily L1 pool from LOCAL TEJ cache (0 FinMind API).
REM    pool_{date}.csv is written by Market_SnapshotCollector (starts 17:30).
REM    2026-07-23 fix: the collector has a TPEx publish-window retry loop and can
REM    finish anywhere from 18:02 to ~18:50 -- i.e. AFTER this task's 18:00 start.
REM    The old code took the newest pool_*.csv unconditionally, so on a race it
REM    silently scored YESTERDAY's pool at yesterday's close and the 綜合分 基準日
REM    stayed one day stale with a green log. Now we insist on pool_<today>.csv:
REM      · not there yet  -> poll every 5 min, up to 75 min (covers the retry window)
REM      · collector already reported success today but still no pool
REM                       -> non-trading day (holiday), quiet no-op, exit 0
REM      · timeout        -> fail loud, keep last good snapshot, exit 1
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "POOL=outputs\universe_pool\pool_%TODAY%.csv"
set /a WAITED=0

:waitpool
if exist "%POOL%" goto poolready
set "HB="
for /f "delims=" %%h in ('powershell -NoProfile -Command "$f='outputs\heartbeat\last_success.txt'; if (Test-Path $f) { $t=(Get-Content $f -Raw).Trim(); if ($t.Length -ge 10) { $t.Substring(0,10) } }"') do set "HB=%%h"
if "%HB%"=="%TODAY%" (
    call :mark "[info] collector finished today but no %POOL% -- non-trading day, nothing to score."
    call :mark "==== daily_auto_update no-op ===="
    exit /b 0
)
if %WAITED% GEQ 75 (
    call :mark "[ERROR] %POOL% still missing after %WAITED% min -- Market_SnapshotCollector stuck or never ran. Skipping build to keep last good snapshot."
    call :mark "==== end with error ===="
    exit /b 1
)
call :mark "[wait] %POOL% not ready (%WAITED% min elapsed), collector still running -- retry in 5 min."
powershell -NoProfile -Command "Start-Sleep -Seconds 300"
set /a WAITED+=5
goto waitpool

:poolready
call :mark "[step1] build-scores starting from %POOL%"
"%PY%" build_cache.py --build-scores --source tej --universe-from "%POOL%" >> "%LOG%" 2>&1
set "RC=%errorlevel%"
call :mark "[step1] build-scores rc=%RC%"
if not "%RC%"=="0" (
    call :mark "[ERROR] build-scores (tej/pool) failed rc=%RC%, skip deploy to keep last good snapshot."
    call :mark "==== end with error ===="
    exit /b 1
)

REM 1b) refresh 市場燈號 regime exposure snapshot -> cloud_cache (best effort, non-fatal).
REM      deploy_scores.py does `git add cloud_cache`, so this snapshot ships to cloud too.
call :mark "[step2] regime_exposure starting"
"%PY%" -m core.regime_exposure >> "%LOG%" 2>&1
set "RC=%errorlevel%"
call :mark "[step2] regime_exposure rc=%RC%"
if not "%RC%"=="0" call :mark "[warn] regime_exposure snapshot refresh failed, keeping last snapshot."

REM 2) sync scores snapshot -> commit -> push (no-op if scores unchanged)
call :mark "[step3] deploy_scores starting"
"%PY%" deploy_scores.py --message "chore: daily auto update scores snapshot" >> "%LOG%" 2>&1
set "RC=%errorlevel%"
call :mark "[step3] deploy_scores rc=%RC%"
if not "%RC%"=="0" (
    call :mark "[ERROR] deploy_scores.py failed rc=%RC% - check git remote / network."
    call :mark "==== end with error ===="
    exit /b 1
)

REM 3) prune logs older than 30 days (best effort). forfiles returns 1 when it
REM    finds nothing old enough to delete -- that is the normal case, not an
REM    error, so its exit code is deliberately ignored here.
call :mark "[step4] prune logs older than 30 days"
forfiles /P "%LOGDIR%" /M daily_update_*.log /D -30 /C "cmd /c del @path" >nul 2>nul
forfiles /P "%MARKDIR%" /M daily_update_*.marker.log /D -30 /C "cmd /c del @path" >nul 2>nul

call :mark "==== daily_auto_update done ===="
exit /b 0

REM =====================================================================
REM  :mark <text>  -- append one timestamped line to BOTH logs.
REM  Callers must capture %errorlevel% into RC BEFORE calling: the echoes
REM  inside here reset it, so "if errorlevel 1" after a call is meaningless.
REM =====================================================================
:mark
echo %~1 %date% %time% >> "%LOG%"
echo %~1 %date% %time% >> "%MARK%"
goto :eof
