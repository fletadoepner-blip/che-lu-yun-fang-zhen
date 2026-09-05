param(
    [ValidateSet('ugat_frap', 'ugat_frap_transyt', 'transyt', 'max_pressure', 'fixed')][string]$Algorithm = 'ugat_frap_transyt',
    [ValidateSet('morning', 'midday', 'evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 4,
    [int]$VisualDelayMs = 0,
    [int]$LiveInterval = 10
)

& (Join-Path $PSScriptRoot 'scripts\run_and_show.ps1') -Algorithm $Algorithm -Period $Period -Steps $Steps -Threads $Threads -VisualDelayMs $VisualDelayMs -LiveInterval $LiveInterval
exit $LASTEXITCODE
