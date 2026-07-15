# =====================================================================
#  Register the TWSE/TPEx market snapshot collector as a Scheduled Task.
#  Run once (double-click register_market_snapshot_task.bat, or:
#      powershell -ExecutionPolicy Bypass -File scripts\register_market_snapshot_task.ps1)
#
#  Schedule : Tue-Sat 08:30, collecting the PREVIOUS trading day (T-1).
#             Why morning: TWSE openapi flips to the new day OVERNIGHT
#             (still served 7/14 at midnight 7/16 in live testing), while TPEx
#             flips same-day ~14:00-16:00. Next morning BOTH boards serve T-1
#             consistently. Evening collection can never be consistent.
#  Catch-up : StartWhenAvailable = if the PC was off at 08:30, runs when back on
#             (both boards keep serving T-1 until ~14:00, so late-morning
#             catch-up still recovers the day).
#  Remove   : powershell -Command "Unregister-ScheduledTask -TaskName 'Market_SnapshotCollector' -Confirm:$false"
# =====================================================================
$ErrorActionPreference = 'Stop'

$taskName = 'Market_SnapshotCollector'
$bat = Join-Path $PSScriptRoot 'market_snapshot_collect.bat'
if (-not (Test-Path $bat)) { throw "not found: $bat" }

$action   = New-ScheduledTaskAction -Execute $bat
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At 08:30
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
              -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
              -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description 'TWSE/TPEx full-market daily snapshot (0 FinMind API) + L1/L2 universe screen (DevLog section 15)' | Out-Null

$t = Get-ScheduledTask -TaskName $taskName
Write-Host "Registered task '$taskName'  State: $($t.State)"
Write-Host "Next run: $((Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime)"
Write-Host "Manual test:  Start-ScheduledTask -TaskName '$taskName'"
