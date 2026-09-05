# API 与模型调用接口说明

本任务主要是**离线模型接口**：模型从 `model/` 加载，输入状态数组，输出相位动作。20 路口平台另有一个 CityFlow 评测入口和数据采集输出。这里没有网络服务端点——和功能一·任务一那个 HTTP 服务不一样，本任务的模型调用是进程内函数接口。

## 1. 模型加载与推理（Python）

```python
import torch
from src.ugat_frap import UGATFRAPController

model = UGATFRAPController("model/frozen_ugat_4x4.pt", max_frap_weight=1.0)
adapter = "model/frap_adapter.pt"
if __import__("pathlib").Path(adapter).exists():
    model.load_adapter(adapter)
model.assert_frozen()   # 强制检查 UGAT 冻结
model.eval()

# 输入 [batch, 20]：12 维车道需求 + 8 维相位 one-hot
state = torch.zeros(20, 20, dtype=torch.float32)
actions = model.choose_actions(state)   # [20] int64，范围 0..7
```

输入输出维度契约见 `contracts/observation.schema.json`、`contracts/control_action.schema.json`；模型版本与维度见 `contracts/model_registry.json`。

## 2. 20 路口平台评测入口

```powershell
# 容器内（镜像由项目 Dockerfile 构建）
python src/run_cityflow.py --period morning --algorithm ugat_frap --steps 7500 --threads 4
```

| 参数 | 取值 | 说明 |
|---|---|---|
| `--period` | morning / midday / evening | 流量时段 |
| `--algorithm` | ugat_frap / max_pressure / fixed | 算法（对比基线） |
| `--steps` | 整数 | 仿真步数 |
| `--threads` | 整数 | CityFlow 线程数 |
| `--decision-interval` | 整数（默认10） | 决策间隔 |

输出：`outputs/metrics.csv`（追加）、`outputs/trace_<algorithm>_<period>.json`（每 10 秒全网记录）、`outputs/live_*.jsonl`（实时轨迹）。

## 3. 采集输出长什么样（D08 接口证据）

`outputs/metrics.csv` 字段：`algorithm, period, steps, wall_seconds, steps_per_second, final_active_vehicles, final_queue_proxy`。

`outputs/trace_<algorithm>_<period>.json` 每条记录：

| 字段 | 类型 | 含义 |
|---|---|---|
| `time_s` | int | 仿真时刻 |
| `active_vehicles` | int | 当前在网车辆数 |
| `scheduled_vehicles` | int | 已按 Excel 时段调度进入仿真的车辆数 |
| `total_demand` | int | 该时段总需求车辆数 |
| `queue_proxy` | int | 20 路口入口车道车辆数合计代理指标 |
| `node_queue_proxy` | list[int] | 各路口排队代理量 |
| `actions` | list[int] | 各路口当前相位动作（0..7） |
| `vehicles` | list[dict] | 车辆道路位置快照（id/road/distance/speed） |

## 4. 车路云接口草案（平台 API 文档里给的，供后续扩展）

```text
POST /v1/vehicle-position       {"vehicle_id":"v-1","time_s":10,"x_m":0,"y_m":0,"speed_mps":8.2}
GET  /v1/signals/{junction_id}  返回当前相位和剩余绿灯时间
POST /v1/signals/{junction_id}/phase  {"phase":0,"effective_at_s":20}（拒绝 0..7 之外与无效节点）
POST /v1/vehicles/{vehicle_id}/advice {"target_speed_mps":9.5,"valid_for_s":10}
```

生产环境应该在 API 网关做鉴权、速率限制、时间戳单调性校验和审计日志；本任务的 CityFlow 运行器只实现离线算法适配接口。

## 5. 可视化

```powershell
python src/dashboard.py outputs/trace_ugat_frap_morning.json --out outputs/dashboard.html
# 或 Windows 一键动态窗口：
powershell -ExecutionPolicy Bypass -File scripts/run_and_show.ps1 -Algorithm ugat_frap -Period morning -Steps 7500 -Threads 4
```

窗口颜色与相位含义见 `reports/雄安新区20路口高保真仿真验证平台报告.docx` 第 9 节（深绿=动作0 东西直行，亮绿=动作1 南北直行，黄绿=动作2 东西保护左转，黄褐=动作3 南北保护左转，橙=动作4 西向，红=动作5 东向，紫=动作6 南向，青蓝=动作7 北向）。
