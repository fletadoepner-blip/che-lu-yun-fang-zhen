# 交付与验收清单

## 不需要跑环境就能查的

- [x] 主交付配置：`configs/cmp1x3.yml`（1×3 绿波）和运行说明 `docs/RUN_CMP_1X3.md`
- [x] 三个工程的代码：`src/`（20路口平台）、`scripts/`（1×3/1×5、4×4、20路口 的运行与训练入口）
- [x] 模型权重：`model/ugat1x5_best.pt`（主交付迁移分支）、`model/frozen_ugat_4x4.pt`、`model/frap_adapter.pt`、`model/official_ugat_best.pt`、`model/ugat_best_1.pt`；4×4 适配器在 `outputs/4x4_frap/4x4_farp_adapter.pt`
- [x] 配置：`configs/cmp1x3.yml`、`cmp1x5.yml`、`farp4x4.yml`、`xiong_an_20.yaml`、`farp_xiong_an_20.yml`、`cmptrain1x5.yml`
- [x] 契约：`contracts/model_registry.json`、`observation.schema.json`、`control_action.schema.json`
- [x] 文档：`docs/` 下的 API、架构、模型设计、训练、消融、接口协议、验收清单、各场景运行说明
- [x] 报告：`reports/` 下的平台报告、1×5 报告、4×4 报告、算法原理说明
- [x] 实验数据：`outputs/1x5_cmp/*.csv|json|png`、`outputs/4x4_frap/*.csv|json|png`、`outputs/xiong_an_20/metrics.csv`
- [x] 静态交付校验：`python scripts/verify_delivery.py`
- [x] 第三方源码：`third_party/CityFlow/`，固定提交 `81ee0f47659ca66177a71f81676691c58ee89184`

## 需要 Docker/CityFlow 环境才能验证的

- [ ] **1×3 绿波（主交付）**：容器里跑 `run_cmp_1x5.py --test_steps 100 --policy cmp`（场景 `cityflow_atlanta1x3`），确认输出 Final Travel Time；9000 步正式跑完把结果放进 `outputs/1x3_cmp/`，并更新 `docs/ABLATION.md` 第 1 节
- [ ] 1×5（中间版本）：容器里 `run_cmp_1x5.py --test_steps 100 --policy cmp`，确认五个 rank 都是 `trainable_parameters=0` 且输出 Final Travel Time
- [ ] 4×4：容器里 `run_farp_4x4.py --test_steps 100`，确认输出 Final Travel Time
- [ ] 20路口：`python src/validate_scenario.py` 输出 `status=PASS, controlled_intersections=20, morning=77749, midday=54864, evening=87051`
- [ ] 20路口：`docker build -t xiong-an-20-platform:final .` 日志里有 `Successfully built CityFlow`；100 步 `ugat_frap` 冒烟退出码 0
- [ ] 模型加载：装好 `torch>=2.0` 后跑 `python -c "import torch; c=torch.load('model/frozen_ugat_4x4.pt', map_location='cpu', weights_only=True); print(sorted(c))"`，确认 key 是 `dense_1.weight/dense_1.bias/dense_2.weight/dense_2.bias/dense_3.weight/dense_3.bias`

## 集成时本机的实际情况（2026-08-28）

集成那台机器上 Python 环境没有 torch/cityflow，Docker 守护进程也没启动，所以这次交付做的是：代码/数据/权重/日志的整合、契约和文档补齐、以及不依赖外部环境的静态验收（`scripts/verify_delivery.py`）。**没有在集成过程中虚构任何仿真结果**；文档里引用的实验数字全部来自 ugat 交付的原始 `outputs/` 文件。1×3 主交付的最终结果需要在容器里按 `docs/RUN_CMP_1X3.md` 补跑后填入 `outputs/1x3_cmp/`；跑完把命令输出、指标 CSV 和截图补进 `outputs/`，作为 D03/D04 的运行证据。
