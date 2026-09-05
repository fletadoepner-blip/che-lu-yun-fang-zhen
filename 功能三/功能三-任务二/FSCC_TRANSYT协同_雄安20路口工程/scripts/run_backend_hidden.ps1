param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$Image,
    [Parameter(Mandatory = $true)][string]$Period,
    [Parameter(Mandatory = $true)][string]$Algorithm,
    [Parameter(Mandatory = $true)][int]$Steps,
    [Parameter(Mandatory = $true)][int]$Threads,
    [Parameter(Mandatory = $true)][int]$LiveInterval,
    [Parameter(Mandatory = $true)][int]$VisualDelayMs,
    [Parameter(Mandatory = $true)][string]$LiveTraceName
)

Set-Location $ProjectRoot
& docker run --rm -v "${ProjectRoot}:/workspace/final" --entrypoint /bin/bash $Image -lc "cd /workspace/final && python src/run_cityflow.py --period $Period --algorithm $Algorithm --steps $Steps --threads $Threads --live-interval $LiveInterval --visual-delay-ms $VisualDelayMs --live-trace /workspace/final/outputs/$LiveTraceName"
exit $LASTEXITCODE
