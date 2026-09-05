# 1x5 Frozen UGAT + C-MP-FRAP Hybrid：复现与训练

## 1. 算法说明

本项目在 1x5 CityFlow 路网中使用冻结 UGAT 与联合 C-MP-FRAP 策略。C-MP 的归一化相位压力、FRAP 的学习型相位关系分数和下游平均占用风险被直接合成为同一个候选相位分数；最终动作由该联合分数的 `argmax` 产生，不存在“先执行 C-MP、再由 FRAP 覆盖”的两阶段决策。UGAT 参数全部冻结，仅作为诊断参考分支。

联合分数为：`1.00 * normalized_pressure + 0.08 * bounded_frap_relation - 0.00 * normalized_downstream_load`。FRAP 输出保持其原始有界尺度，不再单独归一化，避免把随机初始化噪声放大为相位偏好。FRAP 的相位关系参数零初始化，因此在尚未产生真实梯度更新前，联合策略严格复现 C-MP。最小绿灯和下游单车道绝对占用上限仍作为物理可行性约束；若所有候选相位均超过上限，程序不会死锁，而是从全部相位中选择联合分数最高者。`pressure_weight`、`frap_weight`、`downstream_weight` 可在训练和验证中显式设置，三者不应同时为零。

联合动作还使用 `max_normalized_pressure_regret=0.03` 信赖域：FRAP 只能在与最大 C-MP 压力相差不超过 3% 的候选相位中参与排序。这是联合优化的可行域约束，不是“先执行 C-MP、再覆盖”的两阶段逻辑，可防止训练后的 FRAP 项在低压力相位上产生高频错误切换。

联合目标还包含 `action_deviation_penalty=0.005`：任何偏离 C-MP 压力最优相位的候选都会承担固定代价。该项用于排除压力并列时的微小数值噪声；只有 FRAP 产生超过该最小有效幅度的学习收益时，联合最优解才会改变动作。

当前项目的 FRAP adapter 使用三组确定性状态视图：`log1p(lane_count)`、相对于本路口平均车流的负载，以及 `tanh(lane_count / 10)` 饱和度；随后与当前相位和候选相位关系嵌入融合。该处理只进入可训练 FRAP 分支，UGAT 的原始输入、冻结参数和 CityFlow 指标均不改变。相位关系参数采用零初始化，未产生梯度更新时 FRAP 残差严格为零。旧版 FRAP checkpoint 与当前联合策略版本不兼容，必须重新训练，不得混用。

已验证的中性联合策略（`seed=4444`，9000 步）结果为 Travel Time `1019.0249`、queue `8.2642`、delay `0.1465`、throughput `2171`，与 C-MP 基线逐值一致。这是联合模型训练前的正确起点；任何训练产生的模型仍须通过正式门槛，不能以训练内结果替代正式结果。

训练场景可使用多个 CityFlow seed 扩展；每个 seed 都会创建新的仿真世界和车流随机序列。正式评测仍固定为 `seed=4444`，因为当前 C-MP 基线 `1019.0249 / 8.2642 / 0.1465` 正是这一 seed、9000 步、相同网络和相同统计口径下得到的。固定评测 seed 是为了让各 checkpoint 和基线逐项可比，不是要求训练只能使用 `4444`。

## 2. 启动容器

Windows PowerShell：

```powershell
docker run --rm -it --entrypoint /bin/bash -v "C:\Users\lauri\Desktop\1x5ugat+cmp+frap:/workspace/final" danielda1/ugat:latest
```

容器内：

```bash
cd /DaRL/UGAT_Docker
python /workspace/final/scripts/train_cmp_adapter_1x5.py --help
```

## 3. C-MP 基线验证

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x5_cmp_baseline_9000
```

当前已知基线协议为 Travel Time `1019.0249`、queue `8.2642`、delay `0.1465`、throughput `2171`；重新运行应以日志实际输出为准。

## 4. 已验证回退模型

当前项目保留一组与当前环境重新验证通过的旧 C-MP adapter 权重，位于 `logs/legacy_cmp_adapter_best`。在 `seed=4444`、9000 步、`override_advantage=0.15` 下，复验结果为 Travel Time `1008.7886`、queue `8.2007`、delay `0.1451`、throughput `2171`，均优于 C-MP 基线。若新的 C-MP-FRAP 实验模型未通过正式筛选，应使用该回退模型而非未验证 checkpoint。

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp_legacy_adapter --adapter_dir /workspace/final/logs/legacy_cmp_adapter_best --use_best_adapter --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --prefix legacy_cmp_adapter_verified_9000
```

在该 `1008.7886` 起点上继续训练的专用入口为：

```bash
python /workspace/final/scripts/train_legacy_cmp_adapter_1x5.py --thread_num 4 --seed 4444 --episodes 5 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00001 --eval_steps 9000 --independent_validation_steps 9000 --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --max_override_rate 0.02 --bootstrap_verified_best --prefix legacy_continue_round_01
```

第一轮使用 `--bootstrap_verified_best` 从已验证权重创建独立续训候选；后续轮次删除该参数并添加 `--resume_candidate`。该入口使用旧 adapter 架构，与 FRAP checkpoint 目录隔离在 `logs/legacy_cmp_adapter_train`。每轮均以独立 9000 步评测筛选，不能保证达到 `988`，但可避免从不稳定 FRAP 实验模型重新开始。

## 5. FRAP 短训练验证

```bash
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 1 --seed 4444 --episodes 1 --steps 1100 --learning_start 100 --batch_size 16 --learning_rate 0.00003 --eval_steps 9000 --independent_validation_steps 9000 --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --max_override_rate 0.02 --reset_candidate --prefix 1x5_cmp_frap_smoke
```

该命令用于检查 FRAP 前向、反向传播和 checkpoint 保存，不用于正式成绩。应看到 `training_enabled=true`、`trainable_parameters` 以及 `independent_validation_complete`。

## 6. 正式训练

```bash
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 4 --seed 4101 --formal_eval_seed 4444 --episodes 5 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --independent_validation_steps 9000 --pressure_weight 1.00 --frap_weight 0.08 --downstream_weight 0.00 --max_downstream_lane_count 15.0 --reset_candidate --prefix 1x5_joint_cmp_frap_formal
```

每轮会额外启动独立 CityFlow 进程复测 9000 步。`best_rank_<rank>.pt` 的固定正式准入规则为：Travel Time 必须低于基线；queue、delay 中最多一项可高于基线，且单项回退不得超过 `2%`；加权综合分 `0.60 * TT_ratio + 0.25 * queue_ratio + 0.15 * delay_ratio` 必须不高于 `0.99`；联合策略还必须确实产生不同于纯 C-MP 的动作。该规则允许整体改善显著、仅一项辅助指标轻微回退的模型作为正式模型。否则仅保存为候选或恢复上一个候选。

示例 `Travel Time=988.3174`、`queue=8.3602`、`delay=0.1436` 的综合分约为 `0.9818`：Travel Time 改善约 `3.01%`，delay 改善约 `2.00%`，queue 仅回退约 `1.16%`，因此符合该正式准入规则。

## 7. 推荐：多场景正式训练

下列命令用三个训练场景扩展训练分布，同时每次 checkpoint 的独立正式筛选仍严格使用 `seed=4444`。每个场景为 3 个 episode、每个 episode 为 9000 步；时间约为单场景训练的三倍。

```bash
python /workspace/final/scripts/train_cmp_adapter_multiscenario_1x5.py --thread_num 4 --train_seeds 4101,4102,4103 --formal_eval_seed 4444 --episodes 3 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --independent_validation_steps 9000 --pressure_weight 1.00 --frap_weight 0.08 --downstream_weight 0.00 --max_downstream_lane_count 15.0 --queue_penalty 2.0 --delay_penalty 1.0 --queue_tolerance 0.0 --delay_tolerance 0.0 --reset_candidate --prefix 1x5_joint_cmp_frap_multiscenario
```

程序在第一个场景从新版 FRAP 初始化开始；仅当上一场景产生安全 continuation candidate 后，才会进入下一场景继续训练。若没有 candidate，它会停止并打印原因，而不是用不安全模型继续训练。`best_rank_*.pt` 仍只会由固定正式门槛生成。

## 8. 反事实训练

训练器在指定决策点调用 CityFlow `snapshot/load`，从同一仿真状态分别以全 C-MP 动作和联合候选动作推进 120 秒窗口。advantage 同时包含 reward、queue、delay 和归一化 Travel Time 差异；只有候选分支的 advantage 超过 `counterfactual_min_advantage`，该动作才会实际执行并进入 replay。每一条分支对比写入 `logs/counterfactual_rollouts.csv`，最终成绩仍以独立 9000 步指标为准。

推荐正式命令：

```bash
python /workspace/final/scripts/train_cmp_adapter_multiscenario_1x5.py --thread_num 4 --train_seeds 4101,4102,4103 --formal_eval_seed 4444 --episodes 3 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --independent_validation_steps 9000 --pressure_weight 1.00 --frap_weight 0.08 --downstream_weight 0.00 --max_normalized_pressure_regret 0.03 --action_deviation_penalty 0.005 --counterfactual_every 5 --counterfactual_horizon 120 --counterfactual_min_advantage 0.01 --counterfactual_probe_regret 0.25 --counterfactual_travel_weight 1.0 --max_downstream_lane_count 15.0 --queue_penalty 2.0 --delay_penalty 1.0 --run_label counterfactual_round_01 --prefix 1x5_counterfactual_round_01
```

运行时间会高于普通训练：每 5 个决策增加两条 30 秒分支 rollout。看到 `counterfactual ... accepted=True` 表示该样本通过同状态比较；连续 `accepted=False` 表示候选没有真实优势，程序将继续执行 C-MP 而不是记录负样本为改进。

每次出现新的安全候选时，程序同时更新 `logs/cmp_frap_checkpoints/candidate_rank_*.pt` 并在 `logs/cmp_frap_checkpoints/candidate_history/<run_label>/seed_<seed>_episode_<episode>/` 保存不可覆盖副本和 `metrics.json`。下次执行多场景命令时，不带 `--reset_candidate` 即自动从当前版本的全局最佳安全候选继续。`candidate_rank` 仅用于续训，不是正式模型；只有 `best_rank` 才代表通过全部正式门槛。

## 9. 从候选 FRAP 继续训练

```bash
python /workspace/final/scripts/train_cmp_adapter_multiscenario_1x5.py --thread_num 4 --train_seeds 4104,4105,4106 --formal_eval_seed 4444 --episodes 3 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --independent_validation_steps 9000 --pressure_weight 1.00 --frap_weight 0.08 --downstream_weight 0.00 --max_downstream_lane_count 15.0 --queue_penalty 2.0 --delay_penalty 1.0 --queue_tolerance 0.0 --delay_tolerance 0.0 --run_label joint_v2_continue_01 --prefix 1x5_joint_cmp_frap_continue_01
```

续训时不要携带 `--reset_candidate`，否则会丢弃当前全局安全候选。`candidate_rank_*.pt` 只用于继续训练，不能直接作为正式模型。`--train_seeds` 改变每个 CityFlow 训练场景，`--formal_eval_seed 4444` 固定正式评测条件，因此各轮正式指标可以比较。

## 10. 正式 9000 步运行

确认存在 `logs/cmp_frap_checkpoints/best_rank_0.pt` 至 `best_rank_4.pt` 后：

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp_frap --adapter_dir /workspace/final/logs/cmp_frap_checkpoints --use_best_adapter --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --prefix 1x5_cmp_frap_best_9000
```

正式指标写入 `logs/1x5_cmp_simulation_metrics.csv` 与 `logs/1x5_cmp_latest_metrics.json`。没有合格 FRAP checkpoint 时，正式结果使用 C-MP 基线，不得把训练内指标当作正式成绩。
