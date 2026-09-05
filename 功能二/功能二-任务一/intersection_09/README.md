# 独立路口包：五岔路口 j_09（铃铛阁大街221号附近）

从「雄安新区20路口」场景中**独立提取**出的单个五岔路口，可单独跑通。

## 路口类型

- **交叉口类型**：五岔路口（五条进向：N / NE / E / S / W）
- 原始路口编号：`j_09`，名称：**铃铛阁大街221号附近**

## 数据来源

从 `雄安新区20路口_UGAT_FRAP_CityFlow/data/xiong_an_20/roadnet.json` 与
`flow_{morning,midday,evening}.json` 中按路口 `j_09` 提取。所有道路、车道、
相位（lightphases）、转向关系（roadLinks）与原场景一致；仅把通向其他路口的
跨路口道路替换为本地虚拟边界节点，使本路口可脱离 20 路口网格独立运行。

## 文件清单

| 文件 | 说明 |
|------|------|
| `roadnet.json` | 路网（标准 CityFlow 格式） |
| `flow_morning.json` | 早高峰流量 |
| `flow_midday.json` | 平峰流量 |
| `flow_evening.json` | 晚高峰流量 |
| `cityflow.config.json` | 引擎配置 |
| `engine.py` | 轻量纯 Python 仿真引擎（无需 C++/Docker） |
| `run.py` | 纯 Python 运行入口（默认可用） |
| `run_cityflow.py` | 原生 CityFlow 引擎运行入口（需 Linux/Docker） |
| `intersection_info.json` | 本路口提取信息汇总 |

## 运行方式

### 方式一：纯 Python 仿真（本机直接可跑，推荐）

```bash
python run.py --algorithm max_pressure --steps 1500
```

可选参数：
- `--algorithm fixed|max_pressure`
- `--steps`：仿真秒数
- `--period morning|midday|evening`

结果输出到 `outputs/metrics_*.json`。

### 方式二：原生 CityFlow 引擎（Linux / Docker）

```bash
python run_cityflow.py --algorithm max_pressure --steps 7600
```

## 说明

本路口为五岔路口，五个进向（含对角线方向 NE）的车辆经信号灯控制后，
可完成多种转向组合，相位方案与源场景完全一致。
