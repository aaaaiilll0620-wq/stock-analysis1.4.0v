# =====================================================================
#  Register the TWSE/TPEx market snapshot collector as a Scheduled Task.
#  Run once (double-click register_market_snapshot_task.bat, or:
#      powershell -ExecutionPolicy Bypass -File scripts\register_market_snapshot_task.ps1)
#
#  Schedule : weekdays (Mon-Fri) 17:30, collecting SAME-DAY data.
#             TWSE side uses the rwd API (date-addressable, published same
#             afternoon; the openapi snapshot lags until next morning and was
#             abandoned). Target date is driven by TPEx openapi (flips ~14-16h).
#  Catch-up : StartWhenAvailable = if the PC was off at 17:30, runs when back
#             on; a next-morning catch-up still recovers yesterday (TPEx keeps
#             serving T-1 until ~14:00 and TWSE rwd is date-addressed).
#             2026-07-19: added -WakeToRun -- on 7/18 the PC was ASLEEP (not
#             off) at trigger time and the task silently never fired
#             (MissedRuns stayed 0, so StartWhenAvailable did not catch up).
#             WakeToRun wakes the machine from sleep at 17:30; needs wake
#             timers allowed in Windows power settings to be effective.
#  Remove   : powershell -Command "Unregister-ScheduledTask -TaskName 'Market_SnapshotCollector' -Confirm:$false"
# =====================================================================
$ErrorActionPreference = 'Stop'

$taskName = 'Market_SnapshotCollector'
$bat = Join-Path $PSScriptRoot 'market_snapshot_collect.bat'
if (-not (Test-Path $bat)) { throw "not found: $bat" }

# 隱藏視窗執行 (2026-07-16:避免空白主控台被誤關殺掉收集器)。
# 2026-07-23:與 register_daily_task.ps1 一併從 wscript + run_hidden.vbs 換成
# powershell + run_hidden.ps1 —— Windows 11 已把 VBScript 列入淘汰,每次執行
# 都會在 Application 記錄留一筆 VBScriptDeprecationAlert 4096。此處純屬預防性
# 遷移:本任務並未出過事 (對照 FinMind_DailyUpdate 的 exit 255)。
# 包裝器選型與離開碼實測結果見 run_hidden.ps1 檔頭。
$ps1 = Join-Path $PSScriptRoot 'run_hidden.ps1'
if (-not (Test-Path $ps1)) { throw "not found: $ps1" }
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' `
              -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ps1`" `"$bat`""
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 17:30
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
              -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
              -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description 'TWSE/TPEx full-market daily snapshot (0 FinMind API) + L1/L2 universe screen (DevLog section 15)' | Out-Null

$t = Get-ScheduledTask -TaskName $taskName
Write-Host "Registered task '$taskName'  State: $($t.State)"
Write-Host "Next run: $((Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime)"
Write-Host "Manual test:  Start-ScheduledTask -TaskName '$taskName'"
