param(
    [ValidateSet('ugat_frap', 'ugat_frap_transyt', 'transyt', 'max_pressure', 'fixed')][string]$Algorithm = 'ugat_frap_transyt',
    [ValidateSet('morning', 'midday', 'evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 4,
    [int]$VisualDelayMs = 0,
    [int]$LiveInterval = 10,
    [string]$Image = 'xiong-an-20-platform:final'
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
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
    $LiveTrace = Join-Path $ProjectRoot "outputs\live_$($Algorithm)_$($Period)_$RunId.jsonl"
    $LiveTraceName = Split-Path -Leaf $LiveTrace
    $BackendLog = Join-Path $ProjectRoot "outputs\backend_$($Algorithm)_$($Period)_$RunId.log"
    $BackendErr = Join-Path $ProjectRoot "outputs\backend_$($Algorithm)_$($Period)_$RunId.err.log"

    # Keep the simulation/control backend out of the user's visible terminal.
    # The monitor is opened only after the backend has emitted its first frame,
    # so it never remains indefinitely on the preparation screen.
    $backendScript = Join-Path $ProjectRoot 'scripts\run_backend_hidden.ps1'
    $backendArgs = @('-NoProfile', '-WindowStyle', 'Hidden', '-File', $backendScript, '-ProjectRoot', $ProjectRoot, '-Image', $Image, '-Period', $Period, '-Algorithm', $Algorithm, '-Steps', $Steps, '-Threads', $Threads, '-LiveInterval', $LiveInterval, '-VisualDelayMs', $VisualDelayMs, '-LiveTraceName', $LiveTraceName)
    $Backend = Start-Process -FilePath 'powershell.exe' -ArgumentList $backendArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErr -PassThru

    $deadline = (Get-Date).AddSeconds(120)
    while (-not (Test-Path $LiveTrace) -and (Get-Date) -lt $deadline -and -not $Backend.HasExited) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path $LiveTrace)) {
        $detail = @($BackendLog, $BackendErr) | Where-Object { Test-Path $_ } | ForEach-Object { Get-Content $_ -Raw }
        throw "CityFlow did not create a live trace within 120 seconds.`n$detail"
    }
    while ((Get-Item $LiveTrace).Length -eq 0 -and (Get-Date) -lt $deadline -and -not $Backend.HasExited) { Start-Sleep -Milliseconds 200 }

    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) { $pythonw = (Get-Command python.exe).Source }
    $Monitor = Start-Process -FilePath $pythonw -ArgumentList @('.\src\show_live.py', $LiveTrace, '--roadnet', '.\data\xiong_an_20\roadnet.json', '--topology', '.\data\xiong_an_20\topology.json') -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    Wait-Process -Id $Backend.Id
    $Backend.Refresh()
    if (-not (Select-String -Path $LiveTrace -Pattern '"status"\s*:\s*"complete"' -Quiet)) {
        throw "CityFlow simulation did not finish normally. See $BackendLog"
    }
} finally {
    Pop-Location
}
