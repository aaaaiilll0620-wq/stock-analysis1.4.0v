@echo off
chcp 65001 >nul
REM =====================================================================
REM  一鍵 push 程式碼變更 (app.py 等) 到 GitHub -> Streamlit 自動重部署
REM  註:update_and_push.bat 只會提交 cloud_cache/Scores 快照;
REM      程式碼 (app.py/使用說明) 的變更請用這支上傳。雙擊即可執行。
REM =====================================================================
setlocal
cd /d "%~dp0"

where git >nul 2>nul
if not %errorlevel%==0 (
    echo [X] 找不到 git。請先安裝 Git for Windows 或確認已加入 PATH。
    pause & exit /b 1
)

echo == 目前變更 ==
git status --short
echo.

git add app.py docs

git diff --cached --quiet
if %errorlevel%==0 (
    echo [i] app.py / docs 沒有需要提交的變更,結束。
    pause & exit /b 0
)

git commit -m "docs: 使用說明補充 FinMind token 取得、API 用量與建議搜尋檔數"

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%b
echo.
echo == push 到 origin/%BRANCH% ==
git push origin %BRANCH%
if not %errorlevel%==0 (
    echo [!] push 失敗,嘗試設定 upstream 後重試...
    git push -u origin %BRANCH%
    if not %errorlevel%==0 (
        echo [X] push 仍失敗。請檢查 git remote -v 與 GitHub 登入/權限。
        pause & exit /b 1
    )
)

echo.
echo [OK] 完成!Streamlit Community Cloud 會在幾分鐘內自動重新部署。
pause
endlocal
