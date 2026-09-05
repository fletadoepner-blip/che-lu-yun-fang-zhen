param(
    [ValidateSet('morning','midday','evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 1,
    [int]$VisualDelayMs = 50,
    [int]$LiveInterval = 10
)

$工程 = Join-Path $PSScriptRoot 'UGAT_FRAP_TRANSYT协同_雄安20路口工程'
& (Join-Path $工程 'scripts\run_submission.ps1') -Period $Period -Steps $Steps -Threads $Threads -VisualDelayMs $VisualDelayMs -LiveInterval $LiveInterval
exit $LASTEXITCODE
