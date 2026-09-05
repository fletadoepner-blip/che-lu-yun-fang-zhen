# 训练流程

任务三的主线是：**训练 UGAT 框架 → 冻结 UGAT、嵌入 C-MP → CityFlow 里验证 1×3 绿波**。另外还有 1×5（中间版本）、20 路口/4×4（扩展）的 FRAP 适配器训练。无论哪条路，UGAT 基座都是冻住的，只训练适配层。

## 1. 主线：UGAT 怎么训练的（依据官方论文和项目概述）

UGAT 的训练按官方 [DaRL-LibSignal/UGAT](https://github.com/DaRL-LibSignal/UGAT)（[arXiv:2307.12388](https://arxiv.org/abs/2307.12388)）的流程来：

```text
1) 在仿真环境（CityFlow）里预训练 DQN 策略 π_θ，跑 M 轮
2) 用当前策略在仿真和真实环境各跑一轮，收集状态-动作转移数据
3) 训练接地动作转换网络（输出转换动作 â_t 和它的不确定性）
4) 评估时：不确定性 < 阈值 α → 用转换动作；否则保留原动作
5) 每轮结束按历史不确定性均值动态更新阈值 α
```

落到我们的工程里：

- UGAT 权重是团队训练好的：`model/ugat1x5_best.pt`（1×3/1×5 走廊的分层检查点，5 个 rank 共 3393 参数，全部冻结）、`model/frozen_ugat_4x4.pt`（4×4 基座，1008 参数）。
- 训练完就冻结，C-MP 做在线决策，UGAT 只当迁移/参考分支。
- 最后在 CityFlow 的 1×3 走廊上跑 C-MP，和固定配时/无协同策略对比绿波效果。

## 2. 1×3 / 1×5：C-MP 评测与 C-MP-FRAP 残差训练

### 2.1 C-MP 评测（规则控制器，不需要训练）

```bash
# 容器内（danielda1/ugat:latest）
cd /DaRL/UGAT_Docker
# 1×3 冒烟（主交付）
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 1 --test_steps 100 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x3_cmp_smoke
# 1×3 正式 9000 步
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x3_cmp_9000
```

### 2.2 C-MP-FRAP 残差训练（1×5 中间版本，设计要点见 docs/CMP_FRAP_HYBRID_DESIGN.md）

思路是让 C-MP 当老师：只有 C-MP 对候选相位没把握（压力差 ≤ 2.0）时，才允许 FRAP 出来修正；FRAP 残差范围固定 `[-0.25, 0.25]`，替换条件包括达到最小绿灯、`A(a_frap) ≥ 0.15`、每路口单轮覆盖率 ≤ 2%。训练目标：

```
y = reward_frap - EMA(reward_cmp_teacher)
```

用 Double-DQN target + Huber loss + 梯度裁剪，只更新 FRAP 参数。正式准入（独立 9000 步复测）要求：Travel Time 低于基线；queue、delay 最多一项高于基线且不超过 2%；加权综合分 `0.60·TT_ratio + 0.25·queue_ratio + 0.15·delay_ratio ≤ 0.99`；且 `adapter_overrides > 0`。

```bash
# 短训练验证（只看前向/反向/保存是否正常，不算成绩）
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 1 --seed 4444 --episodes 1 --steps 1100 --learning_start 100 --batch_size 16 --learning_rate 0.00003 --reset_candidate --prefix 1x5_cmp_train_smoke

# 正式训练（1×5 场景）
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 4 --seed 4444 --episodes 5 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --max_override_rate 0.02 --prefix 1x5_cmp_safe_teacher_advantage

# 多场景正式训练
python /workspace/final/scripts/train_cmp_adapter_multiscenario_1x5.py --thread_num 4 --train_seeds 4101,4102,4103 --formal_eval_seed 4444 --episodes 3 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --independent_validation_steps 9000 --pressure_weight 1.00 --frap_weight 0.08 --downstream_weight 0.00 --max_downstream_lane_count 15.0 --queue_penalty 2.0 --delay_penalty 1.0 --reset_candidate --prefix 1x5_joint_cmp_frap_multiscenario
```

## 3. 20 路口平台：FRAP 适配器训练（扩展）

```powershell
# 在 Docker 容器内（镜像由项目 Dockerfile 构建，CityFlow 从 third_party 源码编译）
docker run --rm -v "${PWD}:/workspace/final" --entrypoint /bin/bash xiong-an-20-platform:final -lc "cd /workspace/final && python src/train_adapter.py --epochs 20"
```

- 加载 `model/frozen_ugat_4x4.pt`，全部参数 `requires_grad=False`；
- 唯一可训练：FRAP 适配器 + 融合标量（共 1370 参数）；脚本会强制 `assert_frozen()`；
- 训练完 `model/frap_adapter.pt` 更新，要重新跑 7500 步正式评测。

## 4. 4×4 工程：FRAP 适配器训练（扩展）

```bash
cp /workspace/final/configs/farp4x4.yml /DaRL/UGAT_Docker/configs/tsc/farp4x4.yml
cd /DaRL/UGAT_Docker
python /workspace/final/scripts/train_4x4_adapter.py --epochs 10 --state /workspace/final/logs/4x4_farp_adapter.pt
python /workspace/final/scripts/train_4x4_adapter.py --resume --epochs 10 --state /workspace/final/logs/4x4_farp_adapter.pt
```

训练输出在 `outputs/4x4_frap/4x4_training_metrics.csv` 和 `4x4_training_loss.png`。已记录 epoch1 `raw_mse=1981.3280`、epoch2 `1979.1478`——注意这个 loss 是 Q 值的均方误差，绝对尺度被 Q 值放大了，只用来观察训练过程，**不是**交通控制效果指标。

## 5. 固定随机种子

| 工程 | 固定配置 |
|---|---|
| 1×3 / 1×5（主交付） | 正式评测 `seed=4444, test_steps=9000, delay_type=apx, beta=0.60, alpha=0.60` |
| 雄安20路口 | `seed=20260816`（configs/xiong_an_20.yaml），流量生成也是固定种子 |
| 4×4 | 正式评测 `seed=4444, test_steps=3600, delay_type=apx` |

正式结论都要在相同 seed、步数、网络、统计口径下独立复测；单 seed 的结果要扩展到多个 seed 才能当统计结论。

## 6. 训练日志都在哪

- 1×3（主交付）：`outputs/1x3_cmp/`（预留目录，最终结果追加到这里）
- 1×5（中间版本）：`outputs/1x5_cmp/` 下的 `cmp_training_eval.csv`、`cmp_independent_validation.csv`、`counterfactual_rollouts.csv`、`1x5_cmp_adapter_huber_loss.png`、`legacy_cmp_adapter_best/`（已验证回退模型）
- 20路口：`outputs/xiong_an_20/metrics.csv`（历次运行追加）、`trace_*_morning.json`、`dashboard.html`
- 4×4：`outputs/4x4_frap/4x4_training_metrics.csv`、`4x4_training_loss.png`、`4x4_simulation_metrics.csv`
