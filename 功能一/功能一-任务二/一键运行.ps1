param(
    [int]$Duration = 7200,
    [int]$Seed = 42,
    [double]$Gain = -44
)

& "$PSScriptRoot\run_task2.ps1" -Duration $Duration -Seed $Seed -Gain $Gain
exit $LASTEXITCODE
