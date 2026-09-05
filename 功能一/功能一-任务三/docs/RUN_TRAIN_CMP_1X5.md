# 1x5 Frozen UGAT + C-MP：真正训练步骤

当前训练目标是新增的 UGAT residual adapter。UGAT checkpoint 的全部参数保持冻结；C-MP 规则本身不训练。C-MP 是 teacher 和基础动作策略：只在前两名相位压力差不大于 2.0 的不确定状态采集 adapter 样本；adapter 的替代动作还必须比 C-MP 动作高至少 0.15 residual advantage，且每个路口每轮最多覆盖 2% 决策。训练目标是候选动作的实际 reward 减去在线 C-MP teacher reward 基线，训练脚本使用该相对 advantage、replay buffer 和 `loss.backward()` / `optimizer.step()` 更新 adapter。

训练状态分为两类：`best_rank_<rank>.pt` 是通过独立新进程 9000 步复测、同时优于 C-MP 基线且产生实际 adapter 覆盖动作的正式模型；`candidate_rank_<rank>.pt` 是满足安全边界、按 Travel Time/queue/delay 综合评分最优的续训候选模型。后者只用于后续训练，不可直接作为正式结果。被淘汰的训练轮会恢复到该候选模型，避免连续训练累积退化。

## 1. 启动容器

在 Windows PowerShell 输入：

```powershell
docker run --rm -it --entrypoint /bin/bash -v "C:\Users\lauri\Desktop\1x5ugat+C-MP:/workspace/final" danielda1/ugat:latest
```

## 2. 进入框架目录

在容器内输入：

```bash
cd /DaRL/UGAT_Docker
```

## 3. 先检查训练入口

```bash
python /workspace/final/scripts/train_cmp_adapter_1x5.py --help
```

如果能看到 `--episodes`、`--steps`、`--learning_rate`、`--batch_size`，说明入口可用。

## 4. 运行短训练验证

这一步只用于确认配置、反向传播和 checkpoint 保存，不用于最终性能结论：

```bash
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 1 --seed 4444 --episodes 1 --steps 1100 --learning_start 100 --batch_size 16 --learning_rate 0.00003 --reset_candidate --prefix 1x5_cmp_train_smoke
```

`--reset_candidate` 只清除探索性候选模型，不会删除已经通过正式门槛的 `best_rank_*.pt`。

必须看到：

```text
training_enabled=true
frozen_parameters=...
trainable_parameters=...
q_loss=...
saved_trainable_adapter=...
```

## 5. 检查参数是否真正更新

```bash
sha256sum /workspace/final/logs/cmp_adapter_checkpoints/initial_rank_0.pt
sha256sum /workspace/final/logs/cmp_adapter_checkpoints/episode_0_rank_0.pt
cat /workspace/final/logs/cmp_training_loss.csv | tail
```

`initial_rank_0.pt` 与 `episode_0_rank_0.pt` 的 SHA256 必须不同；CSV 中必须有 loss 记录。训练结束后会生成 `logs/1x5_cmp_adapter_huber_loss.png`，它直接绘制 adapter 的 `smooth_l1_loss`（Huber loss）。图使用固定 `0~1e6` symlog 纵轴，便于跨批次比较；原始最小值、最大值和显示范围写入 `logs/1x5_cmp_adapter_huber_loss_summary.json`。只看到 `trainable_parameters=0` 的推理日志，不能证明训练发生。

## 6. 正式训练

建议先使用 5 个 episode 验证流程，再增加训练量：

```bash
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 4 --seed 4444 --episodes 5 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --max_override_rate 0.02 --prefix 1x5_cmp_safe_teacher_advantage
```

每轮结束后会先完成训练进程内诊断，再启动独立 CityFlow 进程作同 seed、同参数、9000 步复测。只有独立复测中 Travel Time 严格小于 `1019.0249`、queue 不高于 `8.2642`、delay 不高于 `0.1465`，且 `adapter_overrides` 大于 0，才会保存为 `best_rank_<rank>.pt`。独立复测记录写入 `logs/cmp_independent_validation.csv`；没有合格 checkpoint 时，正式结果必须使用 C-MP 基线。更长训练可将 `--episodes` 增加到 20。每个 episode 结束后会保存：

```text
logs/cmp_adapter_checkpoints/episode_<episode>_rank_<rank>.pt
```

## 7. 从上一批的最佳训练候选继续训练

先确认候选模型和候选指标存在：

```bash
ls /workspace/final/logs/cmp_adapter_checkpoints/candidate_rank_*.pt
cat /workspace/final/logs/cmp_adapter_checkpoints/candidate_metrics.json
```

然后运行下一批训练。`--resume_candidate` 会加载候选 adapter 权重；优化器状态会重新初始化，但不会重置 adapter 参数：

```bash
python /workspace/final/scripts/train_cmp_adapter_1x5.py --thread_num 4 --seed 4444 --episodes 5 --steps 9000 --learning_start 1000 --batch_size 64 --learning_rate 0.00003 --eval_steps 9000 --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --max_override_rate 0.02 --resume_candidate --prefix 1x5_cmp_resume_teacher_advantage
```

出现 `independent_validation_complete ... overrides=...` 后，先查看独立复测数据；只有随后出现 `new_best_adapter_episode=...`，才说明该轮已通过正式门槛。仅出现 `new_training_candidate` 说明该模型适合作为下一批训练的起点，但尚不能取代 C-MP 基线。

## 8. 加载训练后 adapter 验证

验证自动筛选出的最佳 checkpoint：

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp_adapter --adapter_dir /workspace/final/logs/cmp_adapter_checkpoints --use_best_adapter --cmp_uncertainty_margin 2.0 --override_advantage 0.15 --prefix 1x5_cmp_teacher_best
```

## 9. 必须运行冻结 UGAT 对照

使用完全相同的步数和 seed：

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy ugat --prefix 1x5_ugat_baseline_9000
```

只有当训练后的 adapter 相比冻结 UGAT 在 Travel Time、queue、delay_ratio_apx 上整体改善，且 throughput 没有明显下降时，才可认为训练有效。不要根据 loss 单独判断交通控制效果。
