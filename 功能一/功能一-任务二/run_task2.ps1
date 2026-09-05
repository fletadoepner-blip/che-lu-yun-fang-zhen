param(
    [int]$Duration = 7200,
    [int]$Seed = 42,
    [double]$Gain = -44
)

$ErrorActionPreference = 'Stop'
$Project = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Project)) {
    throw 'Run this file directly. Do not paste its contents into the terminal.'
}

$RunFile = Get-ChildItem -LiteralPath $Project -Recurse -File -Filter 'run_experiment.py' |
    Select-Object -First 1
if ($null -eq $RunFile) {
    throw 'run_experiment.py was not found under this folder.'
}

$Engine = $RunFile.Directory
$PlotFile = Join-Path $Engine 'plot_comparison.py'
$SummaryFile = Join-Path $Engine 'export_summary.py'
$VerifyFile = Join-Path $Engine 'verify_results.py'
foreach ($File in @($PlotFile, $SummaryFile, $VerifyFile)) {
    if (-not (Test-Path -LiteralPath $File)) {
        throw "Required file was not found: $File"
    }
}

Push-Location -LiteralPath $Engine
try {
    & python $RunFile.Name --mode both --duration $Duration --seed $Seed --gain $Gain
    if ($LASTEXITCODE -ne 0) { throw "Simulation failed with exit code $LASTEXITCODE." }

    & python $VerifyFile --min-travel-improvement 10
    if ($LASTEXITCODE -ne 0) { throw "Result acceptance check failed; do not submit these metrics." }

    & python $PlotFile
    if ($LASTEXITCODE -ne 0) { throw "Plot generation failed with exit code $LASTEXITCODE." }

    & python $SummaryFile
    if ($LASTEXITCODE -ne 0) { throw "Summary export failed with exit code $LASTEXITCODE." }

    Write-Host 'Completed. See the results folder for JSON, CSV, PNG, PDF, and XML outputs.'
}
finally {
    Pop-Location
}
