param(
    [ValidateSet('morning','midday','evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 1,
    [int]$VisualDelayMs = 50,
    [int]$LiveInterval = 10,
    [string]$Image = 'xiong-an-20-platform:final'
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Task = Split-Path -Parent $Root
$resultDir = Join-Path $Task '结果\ugat_frap_transyt'
$summary = Join-Path $Root 'outputs\all_periods_metrics.csv'

# Run the selected period with the native dynamic monitor and hidden backend.
& (Join-Path $Root 'scripts\run_and_show.ps1') -Algorithm ugat_frap_transyt -Period $Period -Steps $Steps -Threads $Threads -VisualDelayMs $VisualDelayMs -LiveInterval $LiveInterval -Image $Image

# Print the completed run's metrics directly in the terminal. Reading the
# JSONL completion record avoids legacy rows in outputs/metrics.csv without
# changing the reference runner or its 7500-step metric convention.
$liveFiles = Get-ChildItem (Join-Path $Root "outputs\live_ugat_frap_transyt_$Period_*.jsonl") | Sort-Object LastWriteTime -Descending
if ($liveFiles) {
    $complete = Get-Content $liveFiles[0].FullName | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.status -eq 'complete' } | Select-Object -Last 1
    if ($complete) {
        Write-Host "`n=== COMPLETED RUN ($Period) ===" -ForegroundColor Cyan
        $complete.metrics | Select-Object period,steps,simulation_end_time_s,total_demand,scheduled_vehicles,completed_vehicles_est,throughput_est,average_travel_time_s,estimated_delay_s,final_queue_proxy,final_active_vehicles,frap_override_rate | Format-List
    }
}

# Consolidate all three archived periods so delay and the other metrics are
# visible together after any single dynamic run.
$rows = foreach ($period in 'morning','midday','evening') {
    $file = Join-Path $resultDir "$period\metrics.csv"
    if (Test-Path $file) { Import-Csv $file | Select-Object -Last 1 }
}
if ($rows) {
    $rows | Export-Csv $summary -NoTypeInformation -Encoding utf8BOM
    Write-Host "`n=== ALL PERIODS SUMMARY ===" -ForegroundColor Cyan
    $rows | Select-Object period,average_travel_time_s,estimated_delay_s,final_queue_proxy,final_active_vehicles,throughput_est,frap_override_rate | Format-Table -AutoSize
}
$trace = Join-Path $Root "outputs\trace_ugat_frap_transyt_$Period.json"
if (Test-Path $trace) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) { $pythonw = (Get-Command python.exe).Source }
    $resultViewer = Join-Path $Root 'src\show_results.py'
    $metricsFile = Join-Path $Root 'outputs\metrics.csv'
    Start-Process -FilePath $pythonw -ArgumentList @($resultViewer, $trace, '--metrics', $metricsFile, '--summary', $summary) -WorkingDirectory $Root -WindowStyle Normal
}
Write-Host "综合结果已生成：$summary" -ForegroundColor Green
