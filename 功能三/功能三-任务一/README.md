# 功能三任务一：经典算法与场景适配

本目录是可独立提交和复算的雄安窄路密网经典算法基线包。场景包含 20 个受控路口、三组 15 分钟需求（早/午/晚高峰）和标准八相位控制方案。

## 交付索引

- `src/algorithms.py`：固定配时、MaxPressure、TRANSYT 风格基线实现。
- `src/run_cityflow.py`：统一评测入口；同一场景、流量、时长和指标定义。
- `scripts/run_task3_aligned_baselines.ps1`：固定配时、MaxPressure、TRANSYT 的 Docker 批量启动脚本。
- `scripts/summarize_baselines.py`：将统一运行结果汇总为指标表。
- `data/xiong_an_20/`：路网、三时段交通流、原始配时、拓扑与数据清单。
- `configs/xiong_an_20.yaml`、`configs/baseline_parameter_grid.yaml`：随机种子、仿真参数和基线参数网格；`data/xiong_an_20/source_signal_plans.json` 为原始信号配时。
- `结果/`：历史基线指标汇总及本次最终验证结果；正式复跑结果写入 `结果/任务3对齐复现/`。
- `docs/`：算法、场景适配、公平对比和复现说明。
- `docs/复现、动态运行与指标查看指南.md`：与任务3最终消融版本对齐的构建、复现、动态监视和指标读取方法。

## 复算步骤

推荐使用 Docker 从随提交包附带的 GitHub 官方 CityFlow 固定源码构建（不需要在 Windows 主机安装 Python CityFlow）。提交包现在包含 `third_party/CityFlow/`，构建时不再依赖容器访问 GitHub。

```powershell
python .\src\validate_scenario.py
docker build --no-cache -t xiong-an-task1:cityflow-local .
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_task3_aligned_baselines.ps1 -Period morning -Steps 7500 -Threads 1 -Image xiong-an-task1:cityflow-local
```

镜像内编译的是 `third_party/CityFlow/` 中的官方源码。批量运行完成后使用 `scripts/summarize_baselines.py` 汇总 `metrics.csv`；动态 TRANSYT 运行和自动指标显示按 `docs/复现、动态运行与指标查看指南.md` 执行。

将 `--period` 分别设为 `morning`、`midday`、`evening` 即可获得三时段的完整公平比较结果。所有基线使用相同的 `--steps 7500`、`--decision-interval 10`、单线程和对应时段流量；控制器、相位映射、9 个决策周期 TRANSYT 参数、拓扑偏移和指标计算已与任务3最终消融主线逐文件对齐，详见 `docs/复现、动态运行与指标查看指南.md`。

现有固定配时和 TRANSYT 历史结果已转录至 `结果/历史基线指标汇总.csv`。当前 Docker 环境的完整 7500 步 TRANSYT 验证结果保存在 `结果/最终验证_transyt_morning/`，状态见 `交付完整性检查表.md`。
