# 雄安新区典型路口 · 独立可运行包

从「雄安新区20路口_UGAT_FRAP_CityFlow」场景中挑选并提取了 **3 个典型路口**，
每个路口均为**独立、可单独跑通**的 CityFlow 场景包。

## 路口清单

| 包目录 | 路口类型 | 原始编号 | 路口名称 | 进向 |
|--------|----------|----------|----------|------|
| `intersection_01` | **十字路口** | `j_01` | 雄州路711号附近 | N / E / S / W |
| `intersection_02` | **三岔路口** | `j_02` | 津海大街-奥威路（容和塔北侧） | N / S / W |
| `intersection_09` | **五岔路口** | `j_09` | 铃铛阁大街221号附近 | N / NE / E / S / W |

三个包覆盖了你要求的三种路口类型：十字路口、三岔路口、五岔路口。

## 各包内容（三个包结构一致）

```
intersection_XX/
├── roadnet.json          # 路网（标准 CityFlow 格式）
├── flow_morning.json     # 早高峰流量
├── flow_midday.json      # 平峰流量
├── flow_evening.json     # 晚高峰流量
├── cityflow.config.json  # 引擎配置
├── engine.py             # 轻量纯 Python 仿真引擎（无需 C++/Docker）
├── run.py                # 纯 Python 运行入口（本机直接可跑）
├── run_cityflow.py       # 原生 CityFlow 引擎运行入口（需 Linux/Docker）
├── intersection_info.json# 提取信息汇总
└── README.md             # 该路口说明
```

## 快速开始

进入任一包目录，直接运行（无需任何 C++ / Docker 依赖）：

```bash
cd intersection_01
python run.py --algorithm max_pressure --steps 1500
```

结果（完成率、平均旅行时间、延误）输出到 `outputs/metrics_*.json`。

## 提取说明

数据来自原 20 路口场景的 `data/xiong_an_20/`。每个独立包：
- 完整保留目标路口的道路、车道、信号相位（lightphases）、转向（roadLinks）；
- 将原来通向其它路口的跨路口道路替换为**本地虚拟边界节点**，从而可脱离
  20 路口网格独立运行；
- 流量按该路口的进向 feeder 从原 `flow_*.json` 中抽取，路由改写为该路口内的
  两段（进向 → 出向），保证在单路口内完成完整旅程。

## 使用原生 CityFlow 引擎

数据为**标准 CityFlow 格式**，在装有 `cityflow` 引擎的 Linux/Docker 环境中可直接运行：

```bash
python run_cityflow.py --algorithm max_pressure --steps 7600
```

若本机未安装 CityFlow，请参考原项目 `Dockerfile`，使用官方镜像
`danielda1/cityflow:latest`（或按原项目 `docs/CITYFLOW_INSTALL.md` 源码编译）。
