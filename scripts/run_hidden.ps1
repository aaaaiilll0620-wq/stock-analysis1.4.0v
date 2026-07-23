# =====================================================================
#  隱藏視窗執行器 (取代 run_hidden.vbs)。
#  用法: powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden `
#          -File run_hidden.ps1 "C:\path\to\some.bat"
#
#  為什麼換掉 VBScript:
#    Windows 11 已把 VBScript 列入淘汰 (每次 wscript 執行,Application 記錄
#    都會留一筆 VBScriptDeprecationAlert 4096),遲早會被移除。
#
#  為什麼是 PowerShell 而不是別的:
#    2026-07-23 實測三種包裝,拿一支 `exit /b 7` 的 bat 驗離開碼能不能傳回
#    工作排程器 —— 那是「上次執行結果」欄位的唯一來源,傳丟了就等於失去
#    失敗訊號:
#      wscript + vbs            -> 7  (正確,但 VBScript 要淘汰)
#      conhost --headless       -> 0  (吃掉離開碼,還吐 ANSI 逃逸碼,淘汰)
#      cmd /c 直呼              -> 7  (正確,但會開一個主控台視窗)
#      powershell -WindowStyle Hidden -> 7  (正確,採用)
#
#  注意:排程仍以「使用者已登入」身分執行,不要改成「不論是否登入」。
#  deploy_scores.py 的 git push 走 HTTPS + credential.helper=manager,
#  GCM 在 session 0 非互動環境拿不到 Windows 認證管理員,push 會卡住。
#
#  代價:相較 vbs 會有極短暫的視窗閃爍。要完全無閃爍就得走 session 0,
#  但那會犧牲 git 認證,不划算。
# =====================================================================
param(
    [Parameter(Mandatory = $true)]
    [string]$BatPath
)

if (-not (Test-Path -LiteralPath $BatPath)) {
    Write-Error "run_hidden.ps1: bat not found -> $BatPath"
    exit 1
}

& cmd.exe /c "$BatPath"
exit $LASTEXITCODE
