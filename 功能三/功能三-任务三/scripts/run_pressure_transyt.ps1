param(
    [string]$ProjectRoot = "C:\Users\lauri\Desktop\提交程序汇总\03_功能三_赛道B经典交通管控算法场景适配与优化\任务2_协同优化算法实现\UGAT_FRAP_TRANSYT协同_雄安20路口工程",
    [string]$Image = "xiong-an-20-transyt:ablation",
    [int]$Steps = 7500,
    [int]$Threads = 1
)
$ErrorActionPreference = "Stop"
$taskRoot = Split-Path -Parent $PSScriptRoot
$destRoot = Join-Path $taskRoot "平峰压力扰动试验"
python (Join-Path $PSScriptRoot "build_corrected_pressure_flows.py")
foreach ($level in 10, 20, 30) {
    $flow = "flow_midday_pressure${level}_ordered.json"
    Copy-Item -Force (Join-Path $destRoot $flow) (Join-Path $ProjectRoot "data\xiong_an_20\$flow")
    foreach ($run in @(@{ Algorithm = "fixed"; Folder = "固定配时" }, @{ Algorithm = "ugat_frap_transyt"; Folder = "UGAT_FRAP_TRANSYT" })) {
        $dest = Join-Path $destRoot "压力$level\$($run.Folder)"
        $projectOutput = "/app/平峰压力增大试验/修正压力$level/$($run.Algorithm)"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        $command = "cd /app && mkdir -p '$projectOutput' && python src/run_cityflow.py --period midday --flow-file $flow --algorithm $($run.Algorithm) --steps $Steps --decision-interval 10 --threads $Threads --out-dir '$projectOutput'"
        docker run --rm -v "${ProjectRoot}:/app" --entrypoint /bin/bash $Image -lc $command
        if ($LASTEXITCODE -ne 0) { throw "Pressure +$level% $($run.Algorithm) run failed" }
        Copy-Item -Force (Join-Path $ProjectRoot "平峰压力增大试验\修正压力$level\$($run.Algorithm)\*") $dest
    }
    Copy-Item -Force (Join-Path $ProjectRoot "data\xiong_an_20\$flow") (Join-Path $destRoot $flow)
}
python (Join-Path $PSScriptRoot "build_pressure_report_transyt.py")
