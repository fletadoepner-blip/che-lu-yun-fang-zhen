# 接口协议、插件接入与结果格式

## 算法插件契约

平台算法必须实现 `SignalAlgorithm.choose(states)`。输入是 `numpy.float32` 的 `[N,12]` 数组，N 为受控路口数，当前场景为 20。每行特征顺序为 `WL, WT, WR, EL, ET, ER, NL, NT, NR, SL, ST, SR`，表示各入口方向的左、直、右转需求代理量。

返回值必须为 `numpy.int64[N]`，每个动作只能为 `0..7`。平台执行器统一执行 `action + 1` 映射到 CityFlow 绿灯相位 `1..8`；相位 `0` 是清空相位，插件无权直接下发。违反形状或范围的插件视为接口错误，运行器应终止本次任务而不产生“完成”记录。

最小插件示例：

```python
import numpy as np
from algorithms import SignalAlgorithm

class MyAlgorithm(SignalAlgorithm):
    name = "my_algorithm"
    def choose(self, states: np.ndarray) -> np.ndarray:
        return np.zeros(states.shape[0], dtype=np.int64)
```

在 `src/run_cityflow.py` 的 `build_algorithm` 中登记实例化分支，并在 `contracts/algorithm_registry.json` 登记名称、适配器和模型依赖。独立 UGAT 插件还可通过 `UGAT算法接口_标准化插件/ugat_interface/registry.py` 调用 `registry.register("my_algorithm", MyAlgorithm)`。

## 数据采集与结果格式

- `outputs/metrics.csv`：每次运行一行，包含算法、时段、步数、耗时、吞吐量、队列代理量和旅行时间等指标。
- `outputs/trace_<algorithm>_<period>.json`：JSON 数组；每项包含 `time_s`、`active_vehicles`、`queue_proxy`、`node_queue_proxy` 和全网 `actions`。
- `outputs/live_<algorithm>_<period>.jsonl`：逐行实时轨迹；末行使用 `{ "status": "complete", "metrics": {...} }` 标记正常完成。
- 字段强制约束在 `contracts/result_schema.json`，最小输入样例在 `contracts/observation_example.json`。

## 车路云北向接口

接口草案在 `docs/API.md`。位置上报、信号查询/下发和速度建议均使用 JSON/UTF-8；生产接入必须增加鉴权、速率限制、时间戳单调校验和审计日志。当前交付包实施离线 CityFlow 适配，不开放网络端口。

## 异常处理

缺少 CityFlow 时，运行器以明确错误信息停止；模型权重键不匹配、插件重名、未知算法、观测维度错误、NaN/Infinity 均抛出异常。只有仿真循环完整结束才写入 live trace 的 `complete` 状态，避免将中断运行误判为有效结果。
