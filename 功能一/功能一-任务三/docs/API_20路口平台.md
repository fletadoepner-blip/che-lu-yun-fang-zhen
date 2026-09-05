# 平台算法接入 API

## 控制算法契约

实现 `src.algorithms.SignalAlgorithm`：输入为形状 `[20, 12]` 的浮点数组，输出形状 `[20]` 的 `int64` 相位动作。动作范围 `0..7`，平台内部会映射到 CityFlow 的相位 `1..8`；相位 `0` 永远是 3 秒黄灯/清空相位，不允许算法直接下发。

## 数据采集输出

`outputs/metrics.csv` 保存算法、时段、步数、执行速度、结束活跃车辆数、排队代理量。`outputs/trace_<algorithm>_<period>.json` 每 10 秒记录全网动作和排队代理量。用 `python src/dashboard.py outputs/trace_max_pressure_morning.json` 生成离线 HTML 观测页。

## 车路云接口草案

`POST /v1/vehicle-position`：`{"vehicle_id":"v-1","time_s":10,"x_m":0,"y_m":0,"speed_mps":8.2}`。

`GET /v1/signals/{junction_id}`：返回当前相位和剩余绿灯时间。

`POST /v1/signals/{junction_id}/phase`：`{"phase":0,"effective_at_s":20}`；服务端必须拒绝超出 `0..7` 的相位和无效节点 ID。

`POST /v1/vehicles/{vehicle_id}/advice`：`{"target_speed_mps":9.5,"valid_for_s":10}`。

生产实现应在 API 网关处做鉴权、速率限制、时间戳单调性校验和审计日志；本项目的 CityFlow 运行器只实现离线算法适配接口，不暴露网络服务。
