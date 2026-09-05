# outputs/1x3_cmp（1×3 绿波主交付结果）

这里是功能一·任务三 **1×3 绿波**最终评测结果的预留位置。1×3 和 1×5 共用 `scripts/run_cmp_1x5.py` 入口（用 `configs/cmp1x3.yml` 里的 `world.network: cityflow_atlanta1x3` 切换场景），运行方法见 `docs/RUN_CMP_1X3.md`。

跑完评测后这个目录应该会有：

| 文件 | 内容 |
|---|---|
| `1x3_cmp_simulation_metrics.csv` | 历次运行指标（policy= cmp、test_steps、seed、beta/alpha、Travel Time、throughput、queue、delay_ratio_apx） |
| `1x3_cmp_latest_metrics.json` | 最近一次运行的机器可读摘要 |
| `1x3_cmp_simulation_metrics.png` | 多次运行的指标曲线 |

正式报告引用 1×3 结果时，要同时给出同场景基线对照（固定配时/无协同）并注明 seed、步数和统计口径（见 `docs/ABLATION.md` 第 1 节）。
