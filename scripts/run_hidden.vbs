' =====================================================================
'  隱藏視窗執行器:讓排程任務跑 bat 時不跳出主控台視窗。
'  用法: wscript.exe //B run_hidden.vbs "C:\path\to\some.bat"
'  第二參數 0 = 隱藏視窗;True = 等待 bat 結束並把 exit code 回傳給排程器,
'  排程器的 ExecutionTimeLimit 與「上次執行結果」欄位照常有效。
'  改回可見視窗:把 register_*_task.ps1 內 action 換回直接執行 bat 再重註冊。
' =====================================================================
If WScript.Arguments.Count < 1 Then
    WScript.Quit 1
End If
Set sh = CreateObject("WScript.Shell")
rc = sh.Run("""" & WScript.Arguments(0) & """", 0, True)
WScript.Quit rc
