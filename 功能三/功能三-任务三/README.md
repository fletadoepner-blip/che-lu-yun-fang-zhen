# 任务3：实验验证与消融对比

## 交付范围

本目录针对雄安新区20路口 CityFlow 场景，固定 7500 仿真步、10 步决策间隔、单线程，比较固定配时、TRANSYT-only、UGAT+FRAP（无 TRANSYT）、UGAT+TRANSYT（去 FRAP）、FRAP+TRANSYT（去 UGAT）和完整 UGAT+FRAP+TRANSYT 六组控制器。时段为早高峰、平峰、晚高峰。

## 文件索引

| 验收项 | 交付位置 |
| --- | --- |
| 批量实验命令 | `scripts/run_batch_experiments.ps1` |
| 指标计算和结果整理 | `scripts/summarize_and_plot.py` |
| 原始指标、配置、时空轨迹 | `最终主线原始指标与轨迹/outputs/ablation_transyt/<方法>/<时段>/` |
| 平峰压力扰动原始结果、轨迹与报告 | `平峰压力扰动试验/` |
| 消融汇总、柱状图和热力图 | `最终主线_UGAT_TRANSYT_FRAP/` |
| 可复算 CSV、三张指标柱状图 | `最终主线_UGAT_TRANSYT_FRAP/`（运行复算脚本生成） |
| 完整实验评估报告 | `最终主线_UGAT_TRANSYT_FRAP/雄安新区20路口_UGAT_TRANSYT_FRAP消融实验报告.docx` |

每个原始结果目录包含 `metrics.csv`、`trace_*.json`、`live_*.jsonl` 和本次运行的 `cityflow_*.json`。`metrics.csv` 为最终指标，`trace_*.json` 可用于复算平均/最大队列代理与时空演化，`live_*.jsonl` 保留每个采样时刻的车辆位置和信号动作。

## 复算已归档结果

```powershell
python .\scripts\summarize_and_plot.py
```

该命令从 18 个原始 `metrics.csv` 和轨迹文件重建 `最终主线_UGAT_TRANSYT_FRAP/` 中的汇总 CSV、三张指标图和复算清单；不依赖报告中手填数值。

## 重跑全部实验

需要 Docker、镜像 `xiong-an-20-transyt:ablation`，以及任务2的完整工程目录。默认参数与已归档实验一致。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_batch_experiments.ps1
```

完整重跑会覆盖 `最终主线原始指标与轨迹/outputs/ablation_transyt/` 下的同名输出。若只需审计已有结果，请仅运行复算命令。

## 重复试验与压力扰动

`平峰压力扰动试验/` 保留固定配时与完整 `UGAT+FRAP+TRANSYT` 在 +10%、+20%、+30% 需求梯度下的原始指标、轨迹、配置、汇总 CSV、折线图和实验报告。压力流量文件保留基线记录顺序，仅在文件末尾追加增量车辆，避免新增车辆改变 CityFlow 的随机车道选择序列。

三时段六组消融的当前归档为每组单次正式运行，不能将其误称为多随机种子均值和标准差。`scripts/run_repeated_trials.ps1` 提供每组 3 次重复运行；完成后自动调用 `scripts/summarize_repeats.py`，生成均值、样本标准差和变异系数 CSV，供补充报告中的“波动”字段。

## 结论引用约束

仅引用 `最终主线_UGAT_TRANSYT_FRAP` 中的最终公平消融结果。历史版本不纳入提交目录。
