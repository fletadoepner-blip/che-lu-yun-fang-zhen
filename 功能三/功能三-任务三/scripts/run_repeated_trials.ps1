param(
    [string]$ProjectRoot = "C:\Users\lauri\Desktop\提交程序汇总\03_功能三_赛道B经典交通管控算法场景适配与优化\任务2_协同优化算法实现\UGAT_FRAP_TRANSYT协同_雄安20路口工程",
    [string]$Image = "xiong-an-20-transyt:ablation",
    [int]$Repeats = 3,
    [int]$Steps = 7500,
    [int]$Threads = 1
)

$ErrorActionPreference = "Stop"
$taskRoot = Split-Path -Parent $PSScriptRoot
$outRoot = Join-Path $taskRoot "重复试验结果"
$methods = "fixed", "transyt", "ugat_frap", "ugat_transyt", "frap_transyt", "ugat_frap_transyt"
$periods = "morning", "midday", "evening"

for ($repeat = 1; $repeat -le $Repeats; $repeat++) {
    foreach ($method in $methods) {
        foreach ($period in $periods) {
            $hostOutput = Join-Path $outRoot "repeat_$repeat\$method\$period"
            New-Item -ItemType Directory -Force -Path $hostOutput | Out-Null
            $containerOutput = "/task3/重复试验结果/repeat_$repeat/$method/$period"
            docker run --rm -v "${ProjectRoot}:/app" -v "${taskRoot}:/task3" --entrypoint /bin/bash $Image -lc "cd /app && python src/run_cityflow.py --period $period --algorithm $method --steps $Steps --threads $Threads --out-dir $containerOutput"
        }
    }
}

Write-Host "Repeated outputs written to: $outRoot"
python (Join-Path $PSScriptRoot "summarize_repeats.py")
