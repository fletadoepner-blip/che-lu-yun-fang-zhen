# 实验结果与消融对比

> 先说清楚口径：所有对比都在**相同场景、相同 seed、相同步数、相同统计口径**下做的。`delay_ratio_apx = 1 - 平均车速/限速`，无量纲、通常落在 0..1；早期日志里 `delay_type=real` 输出的是累计真实延迟总量，**不能**和 apx 口径直接比。下面所有数字都能在 `outputs/` 的原始 CSV/JSON 里复算出来；标了"预留"的地方是交付时还没补齐的最终场景结果，按本文协议补跑后填进去就行。

## 0. 场景演进：1×5 → 1×3

任务三一开始是照 1×5 串联走廊做的（对应 `outputs/1x5_cmp/` 的全部材料）。跑下来效果不理想，而且现实中很少见到五六个路口一字排开的长走廊，这个场景本身不够典型。跟组里商量后收敛到 **1×3 走廊，优化了两遍**，作为最终绿波场景。1×5 的材料没删，保留为开发中间版本，方便对照方法演进和参数调整的过程；最终结论以 1×3 为准。

| 场景 | 角色 | 材料位置 |
|---|---|---|
| 1×3 绿波 | **最终交付场景**（C-MP + 冻结 UGAT + CityFlow） | `configs/cmp1x3.yml`、`outputs/1x3_cmp/`（结果预留）、`docs/RUN_CMP_1X3.md` |
| 1×5 | 开发中间版本（弃用原因：效果不佳、现实罕见长串联路网） | `configs/cmp1x5.yml`、`outputs/1x5_cmp/` |
| 4×4 | 扩展消融（UGAT+FRAP） | `outputs/4x4_frap/` |
| 20路口 | 扩展运行记录（UGAT+FRAP） | `outputs/xiong_an_20/` |

## 1. 1×3 绿波（主交付场景，结果预留）

场景是 CityFlow 1×3 串联走廊，`seed=4444`、`test_steps=9000`、`delay_type=apx`，C-MP（β=0.60, α=0.60）+ 冻结 UGAT。

运行命令见 `docs/RUN_CMP_1X3.md`，指标会写进 `outputs/1x3_cmp/1x3_cmp_simulation_metrics.csv`。**这次交付时 1×3 的最终结果还没带出来**，需要按文档在容器里补跑，报告引用时要给出同场景同 seed 的基线对照（固定配时/无协同），并说明绿波带内旅行时间和排队的变化。

## 2. 1×5：C-MP 与冻结 UGAT 对照（中间版本）

场景 CityFlow Atlanta 1×5，`seed=4444`、`test_steps=9000`、`delay_type=apx`。数据在 `outputs/1x5_cmp/1x5_cmp_simulation_metrics.csv` 和 1×5 报告里。

| 策略 | Travel Time (s) | delay_ratio_apx | Throughput | Queue |
|---|---|---|---|---|
| 冻结 UGAT 对照 | 3931.89 | 0.6540 | 1296 | 36.85 |
| C-MP（β=0.60, α=0.60） | **1019.02** | **0.1465** | **2171** | **8.26** |
| 提升 | **-74.09%** | -77.6% | +67.5% | -77.6% |

结论：确定性的 C-MP 明显好于同场景的冻结 UGAT 单策略，说明"规则先验 + 协同压力"在走廊上是有效的——这正是收敛到 1×3 绿波方案的方法基础，也是 C-MP-FRAP 残差训练的安全起点。

## 3. 1×5：C-MP-FRAP 联合策略和已验证的回退模型（中间版本）

| 策略 | Travel Time (s) | delay_ratio_apx | Throughput | Queue |
|---|---|---|---|---|
| C-MP 基线 | 1019.02 | 0.14652 | 2171 | 8.2642 |
| cmp_frap（训练早期，没过准入） | 1021.79 | 0.14780 | 2171 | 8.2929 |
| **legacy adapter（已验证回退模型）** | **1008.79** | **0.14506** | **2171** | **8.2007** |

数据在 `outputs/1x5_cmp/legacy_cmp_adapter_best/{best_metrics.json, revalidation_9000.json}`。legacy adapter 在 `seed=4444`、9000 步独立复测里四项指标都不比 C-MP 基线差，所以作为正式回退模型留着；训练准入规则见 `docs/TRAINING.md` 第 2.2 节。

## 4. 4×4：FRAP 门控权重消融（max_frap_weight 0 / 0.1 / 1.0）

场景 CityFlow hz4x4，`seed=4444`、`test_steps=3600`，冻结 UGAT 基座（`frozen_ugat_4x4.pt`）。数据在 `outputs/4x4_frap/4x4_simulation_metrics.csv`。

| max_frap_weight | Travel Time (s) | delay_ratio_apx | Throughput | Queue | 说明 |
|---|---|---|---|---|---|
| 0.0 | 464.73 | 0.16618 | 2829 | 9.20 | 冻结 UGAT 基线（无 FRAP） |
| 0.1 | 464.74 | 0.16618 | 2829 | 9.20 | FRAP 影响太弱，没改善 |
| 1.0 | **428.71** | **0.15971** | **2912** | **6.85** | Travel Time、延迟、吞吐量、队列都变好 |

单 seed 对照下 `max_frap_weight=1.0`（有效门控 ≈ `sigmoid(fusion)=0.5005`）最优，程序默认值就定成 1.0。**这个结论要 3~5 个随机种子复核后才能当统计结论**，原始数据全部保留。

## 5. 雄安 20 路口：主算法与基线（运行记录，不宣称性能提升）

场景雄安容东 4×5、20 个受控路口、`morning` 时段 7500 步。数据在 `outputs/xiong_an_20/metrics.csv`（历次运行追加）。平台用 `final_active_vehicles`（结束在网车辆数）和 `final_queue_proxy`（结束排队代理量）当运行指标，**只做记录，不做优越性结论**。

| 算法 | steps | final_active_vehicles | final_queue_proxy | 说明 |
|---|---|---|---|---|
| max_pressure | 7500 | 82 | 136 | 基线（多次运行一致） |
| ugat_frap | 7500 | 84~87 | 142~147 | 多轮运行记录 |
| ugat_frap（斜向进口修正后） | 7500 | 84~85 | 142~144 | 最新路网 |

**为什么不下结论**：20 路口平台报告里写得很清楚，斜向进口修正后的新路网还没重新做最大压力的多种子基线对比，所以现在不能把 FRAP 说成"有性能提升"，只算达到"场景、引擎、算法可复现运行"的合格标准。以后要宣称优化，得按 `docs/RUN_XIONG_AN_20.md` 在相同条件（period/steps/threads/seed）下把基线、重复种子和适配器训练都补完。

## 6. 消融体系小结

| 消融类型 | 工程 | 对比对象 | 对应材料 |
|---|---|---|---|
| 走廊协同（绿波） | 1×3（主交付） | C-MP vs 固定配时/无协同 | `outputs/1x3_cmp/`（结果预留） |
| 算法对照（C-MP vs UGAT） | 1×5 | 冻结 UGAT vs C-MP | `outputs/1x5_cmp/` |
| 联合 vs 基线（C-MP-FRAP vs C-MP） | 1×5 | legacy adapter vs C-MP 基线 | `outputs/1x5_cmp/legacy_cmp_adapter_best/` |
| 模块消融（有无 FRAP） | 4×4 | max_frap_weight 0 vs 1.0 | `outputs/4x4_frap/` |
| 主算法 vs 基线（运行记录） | 20路口 | ugat_frap vs max_pressure | `outputs/xiong_an_20/metrics.csv` |
| 压力扰动 | 20路口 | morning/midday/evening 三时段 | `data/xiong_an_20/flow_*.json`（构建脚本 `src/build_xiong_an_20.py`） |

所有表格的数字都能从 `outputs/` 原始 CSV/JSON 复算；正式报告引用时请保留场景、seed、步数和统计口径。
