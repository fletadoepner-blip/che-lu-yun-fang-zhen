param(
    [ValidateSet('transyt')][string]$Algorithm = 'transyt',
    [ValidateSet('morning', 'midday', 'evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 4,
    [int]$VisualDelayMs = 10,
    [int]$LiveInterval = 10,
    [string]$Image = 'xiong-an-task1:cityflow-local'
)

$ProjectRoot = (Resolve-Path (Join-Path -Path $PSScriptRoot -ChildPath '..')).Path
Push-Location $ProjectRoot
try {
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Image $Image is missing. Building the CityFlow image..." -ForegroundColor Yellow
        docker build -t $Image .
        if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }
    }
    # A unique stream avoids a stale monitor retaining the read offset from a
    # previous run whose trace file was overwritten.
    $RunId = Get-Date -Format 'yyyyMMdd_HHmmss'
    $ResultRoot = Join-Path -Path $ProjectRoot -ChildPath 'outputs\dynamic'
    New-Item -ItemType Directory -Force $ResultRoot | Out-Null
    $LiveTrace = Join-Path -Path $ResultRoot -ChildPath ("live_transyt_{0}_{1}.jsonl" -f $Period, $RunId)
    $LiveTraceName = Split-Path -Leaf $LiveTrace
    $monitorArgs = '.\src\show_live.py', $LiveTrace, '--roadnet', '.\data\xiong_an_20\roadnet.json', '--topology', '.\data\xiong_an_20\topology.json'
    $Monitor = Start-Process -FilePath pythonw.exe -ArgumentList $monitorArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    $volume = "${ResultRoot}:/app/out"
    $dockerArgs = @('run', '--rm', '--volume', $volume, $Image, '--period', $Period, '--algorithm', 'transyt', '--steps', $Steps.ToString(), '--threads', $Threads.ToString(), '--live-interval', $LiveInterval.ToString(), '--visual-delay-ms', $VisualDelayMs.ToString(), '--live-trace', ("/app/out/{0}" -f $LiveTraceName), '--out-dir', '/app/out')
    $DockerProcess = Start-Process -FilePath docker.exe -ArgumentList $dockerArgs -WindowStyle Hidden -PassThru
    $DockerProcess.WaitForExit()
    if ($DockerProcess.ExitCode -ne 0) { throw 'CityFlow simulation failed.' }
    $MetricsPath = Join-Path -Path $ResultRoot -ChildPath 'metrics.csv'
    if (-not (Test-Path -LiteralPath $MetricsPath)) { throw "Metrics file was not generated: $MetricsPath" }
    $Metrics = Import-Csv -LiteralPath $MetricsPath | Select-Object -Last 1
    Write-Host ''
    Write-Host 'TRANSYT simulation completed. Metrics:' -ForegroundColor Green
    [ordered]@{
        'algorithm' = $Metrics.algorithm
        'period' = $Metrics.period
        'steps' = $Metrics.steps
        'average_travel_time_s (travel time)' = $Metrics.average_travel_time_s
        'estimated_delay_s (delay)' = $Metrics.estimated_delay_s
        'throughput_est' = $Metrics.throughput_est
        'final_queue_proxy (queue)' = $Metrics.final_queue_proxy
        'final_active_vehicles' = $Metrics.final_active_vehicles
        'freeflow_mean_s' = $Metrics.freeflow_mean_s
        'metrics_file' = $MetricsPath
        'live_trace' = $LiveTrace
    } | Format-Table -AutoSize
} finally {
    Pop-Location
}
