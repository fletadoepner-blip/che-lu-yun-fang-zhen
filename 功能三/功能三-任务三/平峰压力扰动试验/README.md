# 平峰压力梯度试验（最终完整协同版）

本目录只保留固定配时与完整 `UGAT+FRAP+TRANSYT` 控制器在平峰需求分别增加 10%、20%、30% 时的修正实验结果。压力流量文件保留全部基线记录顺序，仅在末尾追加增量车辆，避免新增车辆改变 CityFlow 的随机车道选择序列。

| 压力 | 流量配置 | 原始结果 |
| --- | --- | --- |
| +10% | `flow_midday_pressure10_ordered.json` | `压力10/固定配时/`、`压力10/UGAT_FRAP_TRANSYT/` |
| +20% | `flow_midday_pressure20_ordered.json` | `压力20/固定配时/`、`压力20/UGAT_FRAP_TRANSYT/` |
| +30% | `flow_midday_pressure30_ordered.json` | `压力30/固定配时/`、`压力30/UGAT_FRAP_TRANSYT/` |

每个算法/压力目录包含 `metrics.csv`、轨迹 JSON、实时 JSONL 和运行时配置。对比汇总为 `压力梯度_固定配时_vs_UGAT_FRAP_TRANSYT汇总.csv`，报告和三张折线图均位于本目录。

复算命令：`python ..\scripts\summarize_pressure_transyt.py`
