@echo off
REM =====================================================================
REM  一鍵更新雲端 scores 快照 -> commit -> push (雙擊即可執行)
REM  預設:只同步『目前的』scores。想先重算 scores 再上傳,改成呼叫:
REM        python deploy_scores.py --rebuild-scores
REM  想連原始資料一起更新 (會用 API):
REM        python deploy_scores.py --update-all
REM =====================================================================
setlocal
cd /d "%~dp0"

REM 優先用 python,沒有再試 py 啟動器
where python >nul 2>nul
if %errorlevel%==0 (
    python deploy_scores.py %*
) else (
    py deploy_scores.py %*
)

echo.
echo ============================================
echo  完成。按任意鍵關閉視窗。
echo ============================================
pause >nul
endlocal
