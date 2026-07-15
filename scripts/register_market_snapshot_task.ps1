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
#  Remove   : powershell -Command "Unregister-ScheduledTask -TaskName 'Market_SnapshotCollector' -Confirm:$false"
# =====================================================================
$ErrorActionPreference = 'Stop'

$taskName = 'Market_SnapshotCollector'
$bat = Join-Path $PSScriptRoot 'market_snapshot_collect.bat'
if (-not (Test-Path $bat)) { throw "not found: $bat" }

$action   = New-ScheduledTaskAction -Execute $bat
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 17:30
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
