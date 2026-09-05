# 将 data/xiong_an_20 从“引用功能二-任务二”转为独立数据目录（外发前运行）
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root 'data\xiong_an_20'
$ref  = 'D:\挑战杯揭榜挂帅2026\功能二-任务二\任务2_平台模块开发与集成\data\xiong_an_20'

if (-not (Test-Path $data)) {
    Write-Error "data\xiong_an_20 不存在：$data"
}

$item = Get-Item $data
if ($item.LinkType -eq 'Junction') {
    Write-Host "检测到 junction -> $($item.Target)"
    $tmp = Join-Path $root 'data\xiong_an_20_tmp'
    Copy-Item -Path $ref -Destination $tmp -Recurse -Force
    Remove-Item $data -Force
    Rename-Item $tmp -NewName 'xiong_an_20'
    Write-Host '已转为独立数据目录。'
} else {
    Write-Host 'data\xiong_an_20 不是 junction，已为真实目录，无需转换。'
}

Write-Host '校验：'
python (Join-Path $root 'src\validate_scenario.py')
