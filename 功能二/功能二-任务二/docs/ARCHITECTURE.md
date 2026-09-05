# 平台总体架构与模块边界

```mermaid
flowchart LR
    A[场景配置与车流数据] --> B[CityFlow 仿真引擎]
    B --> C[数据采集器\ncollect_state / vehicle_snapshot]
    C --> D[统一算法适配器\nSignalAlgorithm.choose]
    E[算法插件注册表] --> D
    F[UGAT + FRAP 模型权重] --> D
    D -->|相位动作 0..7| G[执行器\nCityFlow phase 1..8]
    G --> B
    C --> H[轨迹与指标落盘]
    H --> I[离线 Dashboard]
```

## 模块边界

| 模块 | 目录/入口 | 输入 | 输出 | 责任 |
| --- | --- | --- | --- | --- |
| 场景与配置 | `data/xiong_an_20`、`configs` | roadnet、flow、拓扑 | CityFlow 配置 | 固化 20 路口可复现实验输入。 |
| 引擎适配 | `src/run_cityflow.py` | 场景、算法名、运行参数 | 执行步进、原始状态 | 屏蔽 CityFlow 调用细节，保留相位映射。 |
| 数据采集 | `collect_state`、`vehicle_snapshot` | 引擎状态 | `[20,12]` 状态、车辆快照 | 把引擎数据转换为稳定算法输入，并记录可视化数据。 |
| 算法插件 | `src/algorithms.py`、`UGAT算法接口_标准化插件` | 浮点状态 | `[20]` 整数动作 | 通过统一契约替换固定配时、压力控制、TRANSYT 和 UGAT/FRAP。 |
| 结果服务 | `outputs/*.json`、`metrics.csv` | 运行过程数据 | 指标、轨迹、HTML | 输出可审计结果，向仪表盘提供离线数据。 |

## 端到端运行流程

```mermaid
sequenceDiagram
    participant U as 调用者
    participant R as 统一入口
    participant S as CityFlow/场景
    participant P as 算法插件
    participant O as 输出与可视化
    U->>R: 选择场景、算法和时段
    R->>S: 导入 roadnet/flow/config
    loop 每个决策周期
        S-->>R: 路口车道状态
        R->>P: [20,12] observation
        P-->>R: [20] action (0..7)
        R->>S: 设置 phase action+1
        R->>O: 记录 trace 与 metrics
    end
    R->>O: 生成 dashboard.html
    O-->>U: 指标输出和可视化
```
