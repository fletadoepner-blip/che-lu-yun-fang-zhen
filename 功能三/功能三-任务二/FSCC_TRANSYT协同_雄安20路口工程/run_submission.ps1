param(
    [ValidateSet('morning','midday','evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 1,
    [int]$VisualDelayMs = 50,
    [int]$LiveInterval = 10
)

& (Join-Path $PSScriptRoot 'scripts\run_submission.ps1') -Period $Period -Steps $Steps -Threads $Threads -VisualDelayMs $VisualDelayMs -LiveInterval $LiveInterval
exit $LASTEXITCODE
