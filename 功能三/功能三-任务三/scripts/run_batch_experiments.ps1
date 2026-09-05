param(
    [string]$ProjectRoot = "C:\Users\lauri\Desktop\提交程序汇总\03_功能三_赛道B经典交通管控算法场景适配与优化\任务2_协同优化算法实现\UGAT_FRAP_TRANSYT协同_雄安20路口工程",
    [string]$Image = "xiong-an-20-transyt:ablation",
    [int]$Steps = 7500,
    [int]$Threads = 1
)

$ErrorActionPreference = "Stop"
$taskRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $taskRoot "最终主线原始指标与轨迹\outputs\ablation_transyt"
$methods = "fixed", "transyt", "ugat_frap", "ugat_transyt", "frap_transyt", "ugat_frap_transyt"
$periods = "morning", "midday", "evening"

foreach ($method in $methods) {
    foreach ($period in $periods) {
        $hostOutput = Join-Path $outputRoot "$method\$period"
        New-Item -ItemType Directory -Force -Path $hostOutput | Out-Null
        $containerOutput = "/task3/outputs/ablation_transyt/$method/$period"
        docker run --rm -v "${ProjectRoot}:/app" -v "${taskRoot}:/task3" --entrypoint /bin/bash $Image -lc "cd /app && python src/run_cityflow.py --period $period --algorithm $method --steps $Steps --threads $Threads --out-dir $containerOutput"
    }
}

python (Join-Path $PSScriptRoot "summarize_and_plot.py")
