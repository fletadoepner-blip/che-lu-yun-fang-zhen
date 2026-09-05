param(
    [ValidateSet('morning', 'midday', 'evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 1,
    [string]$Image = 'xiong-an-task1:cityflow-local'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path -Path $PSScriptRoot -ChildPath '..')).Path
$OutputRoot = Join-Path -Path $ProjectRoot -ChildPath (Join-Path -Path '结果\任务3对齐复现' -ChildPath $Period)
$Algorithms = 'fixed', 'max_pressure', 'transyt'

docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    docker build -t $Image $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }
}

foreach ($Algorithm in $Algorithms) {
    $HostOutput = Join-Path -Path $OutputRoot -ChildPath $Algorithm
    New-Item -ItemType Directory -Force -Path $HostOutput | Out-Null
    $ContainerOutput = '/app/out'
    $Volume = "${HostOutput}:/app/out"
    & docker run --rm --volume $Volume $Image --period $Period --algorithm $Algorithm --steps $Steps --threads $Threads --decision-interval 10 --out-dir $ContainerOutput
    if ($LASTEXITCODE -ne 0) { throw "Simulation failed: $Algorithm / $Period" }
}

Write-Host "Completed task3-aligned baseline runs: $OutputRoot"
