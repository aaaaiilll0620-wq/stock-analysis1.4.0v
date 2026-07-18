# =====================================================================
#  Register the daily auto-update as a Windows Scheduled Task.
#  Run once (double-click register_daily_task.bat, or:
#      powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1)
#
#  Schedule : weekdays (Mon-Fri) 18:00  -- 30min buffer after Market_SnapshotCollector
#             (17:30) so today's local chip/margin snapshots are already landed;
#             2026-07-17: moved up from 20:30 -- that buffer predated the v4.5
#             local-first chip pipeline (_read_local_chip reads today's
#             institutional_flow_daily snapshot, 0 API) and margin data is
#             inherently published a day late anyway (see data_provider.py
#             _read_local_margin), so waiting until 20:30 bought nothing.
#  Catch-up : StartWhenAvailable = if the PC was off at 18:00, the task runs
#             as soon as it's back on. 2026-07-19: added -WakeToRun -- on 7/18
#             the PC was ASLEEP (not off) at trigger time and the task silently
#             never fired (MissedRuns stayed 0; StartWhenAvailable does NOT
#             cover sleep). WakeToRun wakes the machine at 18:00; needs wake
#             timers allowed in Windows power settings to be effective.
#  Remove   : powershell -Command "Unregister-ScheduledTask -TaskName 'FinMind_DailyUpdate' -Confirm:$false"
# =====================================================================
$ErrorActionPreference = 'Stop'

$taskName = 'FinMind_DailyUpdate'
$bat = Join-Path $PSScriptRoot 'daily_auto_update.bat'
if (-not (Test-Path $bat)) { throw "not found: $bat" }

# 以 wscript + run_hidden.vbs 隱藏視窗執行 (2026-07-16:不再跳出主控台視窗)
$vbs = Join-Path $PSScriptRoot 'run_hidden.vbs'
if (-not (Test-Path $vbs)) { throw "not found: $vbs" }
$action   = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "//B //Nologo `"$vbs`" `"$bat`""
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 18:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
              -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
              -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description 'FinMind stock cache daily update: build_cache.py + deploy_scores.py (push scores snapshot to GitHub/Streamlit Cloud)' | Out-Null

$t = Get-ScheduledTask -TaskName $taskName
Write-Host "Registered task '$taskName'  State: $($t.State)"
Write-Host "Next run: $((Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime)"
Write-Host "Manual test:  Start-ScheduledTask -TaskName '$taskName'"
