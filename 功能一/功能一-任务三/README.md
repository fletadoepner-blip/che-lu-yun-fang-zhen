# 功能一·任务三：智能交通决策模型研究（绿波）

任务三的题目是"智能交通决策模型研究"，说白了就是：**让 AI 决策模型真正解决一次拥堵疏散 / 协同控制问题，并且结果能跑、能复现、能对比**。我们最后走通的方案是 **UGAT + C-MP** 的组合——UGAT 负责把仿真里学到的策略安全搬到真实路网，C-MP 负责路口具体怎么放行，在 **1×3 串联走廊上把绿波跑通**。

## 这一路是怎么过来的

- 最初按 1×5 走廊开发（工程和结果保留在 `outputs/1x5_cmp/`），跑下来效果不理想，而且现实中很少有这么长的串联路网，于是收敛到 **1×3 场景，优化了两遍**，作为主交付。
- 1×5 的材料没删，留着正好说明方法演进过程，方便评委对照中间版本看最终变化。
- UGAT 的官方实现是 [DaRL-LibSignal/UGAT](https://github.com/DaRL-LibSignal/UGAT)，对应论文 [Uncertainty-aware Grounded Action Transformation（arXiv:2307.12388）](https://arxiv.org/abs/2307.12388)；C-MP 见 [arXiv:2407.01421](https://arxiv.org/abs/2407.01421)。

## 交付包里有什么

| 目录 | 内容 |
|---|---|
| `configs/` | 模型配置，`cmp1x3.yml` 是主交付的 1×3 场景（`cmp1x5.yml` 是中间版本） |
| `contracts/` | 模型注册表和输入输出 Schema，把"模型版本、维度、配置"钉死，避免对不上 |
| `model/` | 模型权重（UGAT 分层检查点、FRAP 适配器等）和 `模型版本说明.md` |
| `scripts/` | 三个工程的运行/训练入口，以及 `verify_delivery.py` 静态验收脚本 |
| `src/` | 20 路口平台的实现（UGAT 冻结基座 + FRAP 适配器、CityFlow 评测入口） |
| `data/` | 20 路口数据，**引用功能二-任务二同一份目录**（见 `data/README_数据引用说明.md`） |
| `outputs/` | 各工程实测指标、轨迹、训练曲线；`1x3_cmp/` 是 1×3 最终结果的预留位置 |
| `reports/` | 各工程的完整报告 docx 和算法原理说明 |
| `docs/` | 模型设计、训练、消融对比、接口协议、验收清单和各场景运行说明 |
| `third_party/CityFlow/` | 固定提交的官方 CityFlow 源码（Docker 构建时从源码编译） |

## 怎么跑

### 1×3 绿波（主交付）

1×3 和 1×5 共用 `scripts/run_cmp_1x5.py`（历史命名没改），在官方 UGAT 镜像 `danielda1/ugat:latest` 容器里跑，通过 `configs/cmp1x3.yml` 里的 `world.network: cityflow_atlanta1x3` 切换场景规模：

```powershell
docker run --rm -it --entrypoint /bin/bash -v "${PWD}:/workspace/final" danielda1/ugat:latest
```

```bash
cd /DaRL/UGAT_Docker
cp /workspace/final/configs/cmp1x3.yml /DaRL/UGAT_Docker/configs/tsc/cmp1x3.yml
# 100 步冒烟
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 1 --test_steps 100 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x3_cmp_smoke
# 9000 步正式
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x3_cmp_9000
```

详细步骤见 `docs/RUN_CMP_1X3.md`。

### 其他工程

20 路口平台用项目里的 Dockerfile 从 `third_party/CityFlow` 源码构建镜像；4×4 和 1×5 的运行命令分别见 `docs/RUN_4X4.md`、`docs/RUN_CMP_1X5.md`。

## 先做个快速检查

```powershell
python scripts/verify_delivery.py
```

输出 PASS 就说明目录、契约、权重、数据引用都齐了（不需要 Docker）。`src/validate_scenario.py` 在 Windows 上也能直接跑，会校验 20 路口场景的路网、流量和配时。

## 实验结论长什么样

1×5 中间版本上，C-MP 相比冻结 UGAT 把 Travel Time 从 3931.89s 压到 1019.02s（约 -74%）；1×3 是最终场景，结果数据待容器补跑后填入 `outputs/1x3_cmp/`。完整对比、消融和结论边界见 `docs/ABLATION.md`——里面也写清楚了哪些地方我们**没有**宣称性能提升（比如 20 路口的多种子基线还没做完）。
