# C-MP-FRAP Hybrid：组合算法定义与验证协议

## 1. 目标

将 C-MP 的交通压力先验与 FRAP 的相位关系建模结合为一个安全的残差控制器。组合算法不直接替换 C-MP，而是以 C-MP 为 teacher 和安全基础动作，仅在 C-MP 对候选相位缺乏明显优势时允许 FRAP 修正。

当前项目中的 `TrainableUGATResidual` 是通用 residual adapter，并非完整论文 FRAP 网络。因而本文件将待实现的相位关系 residual 模块称为 FRAP adapter，避免将现有 adapter 误标为 FRAP。

## 2. 三部分职责

| 模块 | 输入 | 输出 | 是否训练 |
|---|---|---|---|
| C-MP | 上游/下游车道车辆数、速度比、当前相位 | 相位压力分数与基础动作 | 否 |
| 冻结 UGAT | 原有状态特征 | frozen Q 值，仅作参考 | 否 |
| FRAP adapter | 状态特征、当前相位、候选相位关系、C-MP 压力特征 | 每个候选相位的 bounded residual score | 是 |

FRAP adapter 应使用相位条件编码和候选相位之间的关系表示，而不是只使用一个与动作无关的普通 MLP。残差范围固定为 `[-0.25, 0.25]`，避免一次更新破坏 C-MP 的稳定策略。

## 3. 动作选择

1. 计算 C-MP pressure scores，得到基础动作 `a_cmp`、top-two pressure margin 和 `p_cmp`。
2. FRAP adapter 输出 residual scores `r_frap(a)`。
3. 计算相对于 C-MP 的候选优势：

   `A(a) = r_frap(a) - r_frap(a_cmp)`

4. 只有同时满足以下条件，才允许使用 `a_frap` 替换 `a_cmp`：

   - 当前相位已达到最小绿灯时间；
   - `pressure_margin <= 2.0`，即 C-MP 处于不确定状态；
   - `a_frap != a_cmp`；
   - `A(a_frap) >= 0.15`；
   - 每个路口单轮覆盖率不超过 `2%`。

否则执行 C-MP 动作。这样组合后的策略是“C-MP 基础策略 + FRAP 小幅修正”，而不是两个策略无条件投票。

## 4. 训练目标

以 C-MP 动作为 teacher 收集样本，只保留 C-MP 不确定状态。训练目标不拟合 UGAT 的绝对 Q 值，而使用相对于 C-MP teacher reward 的 advantage：

`y = reward_frap - EMA(reward_cmp_teacher)`

使用 Double-DQN target、Huber loss、梯度裁剪和冻结 UGAT 参数。每次优化仅更新 FRAP adapter 参数。

## 5. 互相改进机制

- C-MP 为 FRAP 提供可解释的压力先验和安全动作，降低 FRAP 在拥堵状态下的错误探索。
- FRAP 在 C-MP 压力接近时学习局部相位关系和短期 reward 差异，补足 C-MP 只按压力排序的局限。
- FRAP 不能覆盖高置信度 C-MP 决策，避免“平均指标变好但少数路口崩溃”。

## 6. 验证与模型选择

每个 checkpoint 必须启动独立 CityFlow 进程，在完全相同的 seed、配置和 9000 步下复测。只有同时满足以下条件才保存为正式 `best`：

`Travel Time < 1019.0249`；queue、delay 中最多一项高于基线，且该项不超过基线 `2%`；加权综合分 `0.60 * TT_ratio + 0.25 * queue_ratio + 0.15 * delay_ratio <= 0.99`；并且 `adapter_overrides > 0`。

仅 Travel Time 下降而 queue 或 delay 明显上升的模型只能作为诊断候选，不能作为正式结果。若仅一项辅助指标轻微上升、其余指标和加权综合分满足固定准入规则，则可作为正式结果。若没有通过独立复测的 FRAP checkpoint，正式模型仍使用 C-MP baseline。

## 7. 重要限制

组合算法可能优于 C-MP，但不存在仅凭结构就保证改进的结论。必须通过独立 9000 步评测，并至少与 C-MP baseline 进行同 seed 对照。正式报告不得使用训练进程内评测替代独立复测。
