# =====================================================================
#  WP2-6 watchdog — 偵測「快照鏈靜默漏跑」(工單_活體演練保護_第一梯隊)
#  ---------------------------------------------------------------------
#  背景:7/18 兩排程因 PC 睡眠靜默未跑、33 小時無人察覺,漏收快照永久無法回補。
#        WakeToRun 已補上觸發;本 watchdog 是「即使仍漏跑也會被告知」的第二層。
#
#  兩個訊號 (任一觸發即 ALERT,非破壞性:寫醒目 ALERT 檔 + best-effort toast):
#    1) 心跳陳舊:outputs\heartbeat\last_success.txt 距今 > MaxHeartbeatHours
#       (直接抓「整條鏈根本沒跑」— 即 7/18 的失效模式)。
#    2) pool 落後:outputs\universe_pool 最新 pool_YYYY-MM-DD.csv 日期 < 前一交易日
#       (鏈有跑但沒產出新凍結件)。無網路假日日曆,故用營業日 (Mon-Fri) 近似;
#       連假可能偽陽,但 watchdog 只發提示不阻斷,寧可多叫一次。
#
#  排程 (系統設定變更,請自行執行一次;模式照抄 register_market_snapshot_task.ps1):
#    $a=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\snapshot_watchdog.ps1"'
#    $t=New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At 09:00
#    Register-ScheduledTask -TaskName 'Market_SnapshotWatchdog' -Action $a -Trigger $t -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force
#  手動測試:  powershell -ExecutionPolicy Bypass -File scripts\snapshot_watchdog.ps1
# =====================================================================
param(
    [double]$MaxHeartbeatHours = 26.0    # 日排程 17:30 → 隔日早上檢查,26h 容許時間漂移
)
$ErrorActionPreference = 'Stop'

$repo    = Split-Path -Parent $PSScriptRoot
$hbDir   = Join-Path $repo 'outputs\heartbeat'
$poolDir = Join-Path $repo 'outputs\universe_pool'
$hbFile  = Join-Path $hbDir 'last_success.txt'
$now     = Get-Date

$alerts = @()

# --- 訊號 1:心跳陳舊 ---
if (-not (Test-Path $hbFile)) {
    $alerts += "無心跳檔 ($hbFile)——快照鏈從未成功完成,或 heartbeat 未寫入。"
} else {
    $raw = (Get-Content $hbFile -Raw).Trim()
    # PS 5.1 陷阱:[ref] 目標須為具型別 DateTime,否則 TryParse 多載無法解析 (MethodCountCouldNotFindBest)。
    [DateTime]$hbTime = [DateTime]::MinValue
    if (-not [DateTime]::TryParse($raw, [ref]$hbTime)) {
        # 退回檔案修改時間
        $hbTime = (Get-Item $hbFile).LastWriteTime
    }
    $ageH = ($now - $hbTime).TotalHours
    if ($ageH -gt $MaxHeartbeatHours) {
        $alerts += ("心跳陳舊:上次成功 {0:yyyy-MM-dd HH:mm} ({1:N1} 小時前 > {2} h)——快照鏈疑似漏跑。" -f $hbTime, $ageH, $MaxHeartbeatHours)
    }
}

# --- 訊號 2:pool 日期落後前一交易日 ---
$prev = $now.Date.AddDays(-1)
while ($prev.DayOfWeek -eq 'Saturday' -or $prev.DayOfWeek -eq 'Sunday') { $prev = $prev.AddDays(-1) }

$poolFiles = @(Get-ChildItem -Path $poolDir -Filter 'pool_*.csv' -ErrorAction SilentlyContinue)
if ($poolFiles.Count -eq 0) {
    $alerts += "找不到任何 pool_*.csv ($poolDir)。"
} else {
    $dates = foreach ($f in $poolFiles) {
        if ($f.Name -match 'pool_(\d{4}-\d{2}-\d{2})\.csv') {
            [DateTime]::ParseExact($Matches[1], 'yyyy-MM-dd', $null)
        }
    }
    $newest = ($dates | Sort-Object -Descending | Select-Object -First 1)
    if ($newest -lt $prev) {
        $alerts += ("最新 pool 日期 {0:yyyy-MM-dd} 落後前一交易日 {1:yyyy-MM-dd}——新凍結件未產出。" -f $newest, $prev)
    }
}

# --- 判定 ---
if ($alerts.Count -eq 0) {
    Write-Host ("[watchdog OK] {0:yyyy-MM-dd HH:mm}  心跳與 pool 日期均新鮮。" -f $now)
    exit 0
}

$body = ($alerts -join "`r`n")
if (-not (Test-Path $hbDir)) { New-Item -ItemType Directory -Path $hbDir -Force | Out-Null }
$alertFile = Join-Path $hbDir ("ALERT_{0:yyyyMMdd_HHmmss}.txt" -f $now)
$header = "==== 快照鏈告警 {0:yyyy-MM-dd HH:mm:ss} ====" -f $now
Set-Content -Path $alertFile -Value ($header + "`r`n" + $body) -Encoding UTF8
Write-Warning $header
Write-Warning $body
Write-Host "[watchdog] 已寫 ALERT 檔: $alertFile"

# --- best-effort Windows toast (無 BurntToast/WinRT 也不致命;ALERT 檔才是可靠訊號) ---
try {
    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $tmpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
              [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $tmpl.GetElementsByTagName('text')
    $texts.Item(0).AppendChild($tmpl.CreateTextNode('⚠️ 快照鏈告警')) | Out-Null
    $texts.Item(1).AppendChild($tmpl.CreateTextNode($alerts[0])) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($tmpl)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('FinMind.Watchdog').Show($toast)
} catch {
    Write-Host "[watchdog] toast 不可用 (無妨,ALERT 檔已寫): $($_.Exception.Message)"
}

exit 1
