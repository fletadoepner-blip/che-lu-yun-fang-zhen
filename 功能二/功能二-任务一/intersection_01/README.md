# 独立路口包：十字路口 j_01（雄州路711号附近）

从「雄安新区20路口」场景中**独立提取**出的单个十字路口，可单独跑通。

## 路口类型

- **交叉口类型**：十字路口（四条进向：N / E / S / W）
- 原始路口编号：`j_01`，名称：**雄州路711号附近**

## 数据来源

从 `雄安新区20路口_UGAT_FRAP_CityFlow/data/xiong_an_20/roadnet.json` 与
`flow_{morning,midday,evening}.json` 中按路口 `j_01` 提取。所有道路、车道、
相位（lightphases）、转向关系（roadLinks）与原场景一致；仅把通向其他路口的
跨路口道路替换为本地虚拟边界节点，使本路口可脱离 20 路口网格独立运行。

## 文件清单

| 文件 | 说明 |
|------|------|
| `roadnet.json` | 路网（标准 CityFlow 格式） |
| `flow_morning.json` | 早高峰流量（约 3998 辆） |
| `flow_midday.json` | 平峰流量 |
| `flow_evening.json` | 晚高峰流量 |
| `cityflow.config.json` | 引擎配置 |
| `engine.py` | 轻量纯 Python 仿真引擎（无需 C++/Docker） |
| `run.py` | 纯 Python 运行入口（默认可用） |
| `run_cityflow.py` | 原生 CityFlow 引擎运行入口（需 Linux/Docker） |
| `intersection_info.json` | 本路口提取信息汇总 |

## 运行方式

### 方式一：纯 Python 仿真（本机直接可跑，推荐）

无需任何 C++ / Docker 依赖，用内置轻量引擎验证跑通：

```bash
python run.py --algorithm max_pressure --steps 1500
```

可选参数：
- `--algorithm fixed|max_pressure`：固定相位 / 最大压力控制（默认 max_pressure）
- `--steps`：仿真秒数（默认 3600；早高峰流量分布在 7200s，建议 ≥ 7600 跑完全部车辆）
- `--period morning|midday|evening`：选择流量时段（默认 morning）

运行结果输出到 `outputs/metrics_*.json`，包含：
`throughput`（完成率）、`average_travel_time_s`、`estimated_delay_s` 等。

### 方式二：原生 CityFlow 引擎（Linux / Docker）

数据为标准 CityFlow 格式，在装有 `cityflow` 引擎的环境下运行：

```bash
python run_cityflow.py --algorithm max_pressure --steps 7600
```

若未安装 CityFlow，请参考原项目 `Dockerfile` 使用官方镜像 `danielda1/cityflow:latest`。

## 本路口转向示意（roadLinks）

以 `feed_01_W -> exit_01_S` 为左转、`feed_01_W -> exit_border_01_E` 为直行、
`feed_01_W -> exit_01_N` 为右转等，相位方案与源场景完全一致。
