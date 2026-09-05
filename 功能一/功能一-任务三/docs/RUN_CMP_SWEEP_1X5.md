# 多参数、多 seed 复核

C-MP 是确定性规则控制器，没有神经网络学习率、batch 或反向传播 loss。为了避免用单次运行判断效果，建议在相同流量和仿真步数下复核多个 `beta/alpha/seed` 组合。

在 Docker 容器内，可直接用自动脚本完成 3 组参数 × 3 个随机种子的评测：

```bash
cd /DaRL/UGAT_Docker
python /workspace/final/scripts/run_cmp_sweep_1x5.py --steps 9000 --seeds 4444,4445,4446 --pairs 0.40:0.40,0.60:0.60,0.80:0.60
```

脚本生成 `logs/1x5_cmp_sweep_summary.csv`，按 Travel Time 均值、queue 均值和 throughput 排序。选择规则：优先选择 Travel Time、queue、delay_ratio_apx 均较低且 throughput 不下降的组合；至少使用三个 seed 的均值和标准差，不以诊断 MSE 单独判定控制效果。图 `1x5_cmp_diagnostic_loss.png` 使用原始分数 MSE，不强制落在 0–1。
