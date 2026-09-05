# 雄安新区 20 路口 UGAT + FRAP + CityFlow

本项目把给定的 20 份路口流量和配时工作簿整合为一个可复现的 4 x 5、20 个受控路口 CityFlow 场景。布局是依据随附高德截图、地标和道路走向整理的近似拓扑，用于控制算法实验，不是测绘级 GIS 或车道级高精地图。

## 交付内容

- `data/xiong_an_20/roadnet.json`：一个联动的 20 控制节点 CityFlow 路网；每节点保留四向进口、外部边界和相邻节点连接。
- `data/xiong_an_20/flow_{morning,midday,evening}.json`：从所有 Excel 的 15 分钟左/直/右转量逐车生成的三时段需求。
- `data/xiong_an_20/source_signal_plans.json`：原始 Excel 配时，不会被 FRAP 控制策略覆盖或伪造为训练标签。
- `src/ugat_frap.py`：冻结 UGAT Q 网络与可训练 FRAP 适配器，所有 20 个节点批量推理。
- `src/run_cityflow.py`：CityFlow 评测入口；`src/train_adapter.py`：只训练 FRAP 适配器。
- `src/validate_scenario.py`：不依赖 CityFlow 的 JSON、路由、流量守恒和冻结参数校验。
- `third_party/CityFlow/`：固定官方 CityFlow 源码及 pybind11/rapidjson 子模块；Docker 构建时从源码编译 Python 扩展。

## 快速开始

在本目录执行：

```powershell
python .\src\build_xiong_an_20.py --source-dir "C:\Users\lauri\Desktop\路口数据\路口数据"
python .\src\validate_scenario.py
python .\src\train_adapter.py --epochs 20
python .\src\run_cityflow.py --period morning --steps 7500
python .\src\run_cityflow.py --period morning --algorithm transyt --steps 7500 --threads 1
python .\src\build_report.py
```

需要在仿真运行时自动弹出 Windows 动态路网窗口时，输入：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_and_show.ps1 -Algorithm ugat_frap -Period morning -Steps 7500 -Threads 4
```

`validate_scenario.py` 在 Windows 上即可运行。CityFlow 使用官方项目 [cityflow-project/CityFlow](https://github.com/cityflow-project/CityFlow)；Docker 构建阶段会直接编译 `third_party/CityFlow`，不依赖镜像内预装的 CityFlow 二进制。项目运行器不会伪造 CityFlow 结果：缺少引擎时会明确报错。

## 模型约束与优化

- 共享 UGAT 基座的 `requires_grad=False`，检查点采用项目提供的 4x4 UGAT 基座；不对其做微调。
- FRAP 适配器、融合标量是唯一可学习参数；训练脚本会强制检查冻结约束。
- 20 个节点统一打包为一个张量推理，使用 `torch.inference_mode()`，避免逐节点 Python/torch 调用。
- 固定随机种子、稳定拓扑、确定性流量生成，支持复验。

## 重要建模说明

每一份表给出的都是该路口的观测进口需求。为同时保留 20 个路口的实测进口量并形成联动网络，车辆从节点本地虚拟边界进口进入；若转向方向有相邻控制节点，则继续通过该节点再驶离。这样每个节点的原始进口量可审计，且相邻节点会接收传播交通。没有邻居的方向在边界离网。

配时表的相位文字和周期不完全一致，且各路口相位数不同。因此它们作为原始基准配时元数据保留；算法实验采用适用于全网的标准八相位保护左转/直右相位集，而不是错误地把异构配时强行映射成同一信号方案。

## TRANSYT 风格基线

`transyt` 是本项目的可审计研究复现，不是 PTV TRANSYT 官方软件包。控制器按入口需求计算 Webster 风格绿信比、90 秒公共周期和基于网格传播时间的偏移，每 30 个决策步更新一次方案。结果写入 `outputs/metrics.csv` 和 `outputs/trace_transyt_<period>.json`，报告由 `src/build_report.py` 生成。

## UGAT+FRAP 与 TRANSYT 深度协同

`ugat_frap_transyt` 不是将两套算法同时写入同一信号灯。TRANSYT 作为全网层控制器提供 90 秒公共周期、绿信比和走廊相位偏移；冻结的 UGAT+FRAP 作为局部响应层，仅当其候选相位的入口压力至少高出 TRANSYT 当前相位 5%，且该相位确实处于低效/拥堵状态、并满足 1 个决策步的最小绿灯约束时才接管。每一决定周期最终仅输出一个相位动作。该门控在相同早高峰 7,500 步复测中将平均旅行时间从纯 TRANSYT 的 1221.412 s 降至 1149.833 s。

```powershell
python .\src\run_cityflow.py --period morning --algorithm ugat_frap_transyt --steps 7500 --threads 1
```

结果会额外记录 `frap_override_count`、`frap_override_rate` 和 `transyt_frap_agreement_rate`，用于审计局部接管是否过于频繁或协同失效。
