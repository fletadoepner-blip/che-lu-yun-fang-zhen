# 1×3 绿波：复现与评测说明（主交付场景）

## 1. 这个场景是什么

1×3 绿波是功能一·任务三的**最终交付场景**：一条 3 路口的串联走廊，冻结 UGAT + C-MP 协同控制，在 CityFlow 里仿真验证绿波带效果。

- 来龙去脉：最早是照 1×5 走廊做的（`docs/RUN_CMP_1X5.md`），跑下来效果不理想，现实中也很少有这么长的串联路网，就收敛到 1×3 并优化了两遍；
- 决策机制：C-MP 压力公式（β=0.60, α=0.60）+ 冻结 UGAT 参考分支，联合分数和信赖域见 `docs/MODEL_DESIGN.md`；
- 评测口径：`seed=4444`、`test_steps=9000`、`delay_type=apx`，指标是 Travel Time / throughput / queue / delay_ratio_apx。

## 2. 前提

- Docker 可用，先拉官方 UGAT 镜像：`docker pull danielda1/ugat:latest`
- 1×3 的 CityFlow 场景配置（`cityflow_atlanta1x3.cfg`）应该在镜像的 `/DaRL/UGAT_Docker/configs/sim/` 里；如果镜像里只有 1×5 的，就照 `cityflow_atlanta1x5.cfg` 的结构生成 1×3 版本（去掉尾部两个路口和它们的连接），或者让团队直接提供。

## 3. 运行步骤

Windows PowerShell：

```powershell
docker run --rm -it --entrypoint /bin/bash -v "${PWD}:/workspace/final" danielda1/ugat:latest
```

容器内：

```bash
cd /DaRL/UGAT_Docker
# 把 1×3 配置放进框架的配置目录
cp /workspace/final/configs/cmp1x3.yml /DaRL/UGAT_Docker/configs/tsc/cmp1x3.yml
# 100 步接口验证
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 1 --test_steps 100 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x3_cmp_smoke
# 正式 9000 步评测（C-MP）
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x3_cmp_9000
```

> 说明：`run_cmp_1x5.py` 是 1×3/1×5 共用的入口（历史命名没改），通过 `configs/cmp1x3.yml` 里的 `world.network: cityflow_atlanta1x3` 和镜像内的 CityFlow 场景配置来切换网络规模。

## 4. 输出和结果整理

- 每次运行往宿主机 `outputs/1x3_cmp/1x3_cmp_simulation_metrics.csv` 追加，并更新 `1x3_cmp_latest_metrics.json`、`1x3_cmp_simulation_metrics.png`；
- 正式结论要带**同场景基线对照**（固定配时或无协同的单点控制），给出绿波带内平均旅行时间、排队、通过量的变化；
- 至少用 3 个随机种子重复，报告均值和标准差，才能算统计结论；
- 跑完把 `outputs/1x3_cmp/` 下的 CSV/JSON/PNG 和运行截图补进 `docs/ABLATION.md` 第 1 节和提交报告。

## 5. 成功标准

- 100 步冒烟输出 `Final Travel Time`，退出码 0；
- 9000 步正式运行完成，`metrics.csv` 里出现 `policy=cmp`、`test_steps=9000`、`seed=4444` 的那一行；
- 报告引用 1×3 结果时注明场景、seed、步数和基线对照，别跟其他场景/口径混着用。
