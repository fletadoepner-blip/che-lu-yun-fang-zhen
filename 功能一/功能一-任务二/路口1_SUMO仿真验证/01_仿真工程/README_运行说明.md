# deta-1 自适应信号控制 SUMO 仿真工程

## 策略说明

策略为**需求基础配时与实时排队压力相结合的自适应信号控制**。路口采用左转、直行、右转专用车道和四个分离相位。自适应方案使用联合标定的 `42/30/47/21` 秒基础绿灯，再在每个绿灯相位开始时读取专用车道停车车辆数，以 `gain=-44` 进行负反馈修正。黄灯、全红和相位顺序保持不变。

## 数据与场景

`scenario/demo_1_流量和配时方案.xlsx` 是赛题“路口数据/1”的流量与配时输入。每次运行前，`prepare_dataset1_scenario.py` 会从该 Excel 自动生成：

- `dataset_1.net.xml`：四进口、三车道/进口的 SUMO 路口网络
- `dataset_1.rou.xml`：早高峰 8 个 15 分钟区间、共 96 条交通流
- `dataset_1.add.xml`：Excel 早高峰四相位固定信号程序
- `dataset_1.sumocfg`：SUMO 配置

车道规则：SUMO 车道 `2` 位于道路最左侧，仅左转；车道 `1` 位于中间，仅直行；车道 `0` 位于最右侧，仅右转。信号相位依次为东西直行/右转、东西左转、南北直行/右转、南北左转。

共享转向/直行车道会迫使同轴多转向同时放行，并可能使转向队列阻塞直行车。逐进口单独放行虽可消除冲突，但相位损失过大。本版采用专用车道和四相位，在安全分离与通行效率之间折中。

参数优化采用两阶段搜索：先保持总绿灯预算 140 秒，搜索四相位基础绿灯组合；再扫描压力系数。候选参数必须满足完成车辆数不低于固定方案且四项效率指标全部下降，并使用随机种子 41、42、43 检查稳定性。单种子数值更高但跨种子失稳的 `gain=-52` 被剔除，最终采用稳定的 `gain=-44`。

## 环境

需要 Python 3.10+、SUMO 1.19+，且 `sumo`/`sumo-gui` 可通过系统 `PATH` 找到。若已设置 `SUMO_HOME`，程序会自动使用该目录。

安装 Python 依赖：

```powershell
python -m pip install -r .\requirements.txt
```

设置 SUMO 环境变量：

```powershell
$env:SUMO_HOME='SUMO 安装目录'
```

## 运行

在本目录执行：

```powershell
# 运行固定配时与自适应方案，仿真早高峰 7200 秒
python .\run_experiment.py --mode both --duration 7200

# 结果有效性校验：等待时间非零、完成车辆数不下降、旅行时间改善不少于 10%
python .\verify_results.py --min-travel-improvement 10

# 生成并显示性能对比图
python .\plot_comparison.py

# 生成可审计的 CSV 汇总
python .\汇总结果.py
```

## 一键运行（推荐）

在“任务2_算法逻辑与可视化验证”目录中，任选一种方式：

1. 双击 `run_task2.bat`；
2. 在 PowerShell 中执行以下**完整命令**：

```powershell
& ".\run_task2.ps1"
```

如因本机执行策略受限，也可使用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\run_task2.ps1"
```

请执行脚本文件本身，不要把 `.ps1` 文件中的多行代码逐行粘贴到终端。`run_task2.ps1` 使用全英文 ASCII 内容，可避免 Windows PowerShell 的中文脚本编码解析问题；上述入口会一次完成固定/自适应仿真、绘图和 CSV 汇总。

也可双击 `启动性能对比图.bat`，无需配置 PyCharm 的工作目录。

## SUMO-GUI 可视化

运行下面命令后将自动打开 SUMO-GUI。可通过窗口工具栏暂停、调整仿真速度、缩放路口，并观察车辆排队与灯色切换。

```powershell
python .\run_experiment.py --mode adaptive --gui --duration 7200
```

也可双击 `启动SUMO-GUI_自适应.bat`。

固定配时 GUI 对照：

```powershell
python .\run_experiment.py --mode fixed --gui --duration 7200
```

## 结果文件

- `results/metrics_fixed.json`：固定配时汇总指标
- `results/metrics_adaptive.json`：自适应方案汇总指标
- `results/performance_comparison.png`：基础性能对比图
- `results/tripinfo_*.xml`：车辆级 SUMO 仿真输出
- `verify_results.py`：提交前结果有效性校验；不满足阈值会以非零退出码失败。
