# API 接口说明

基础地址：`http://127.0.0.1:5000`。所有 JSON 使用 UTF-8；错误响应统一为 `{"error":"说明"}`。

## 1. 健康检查与场景元数据

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 查看服务和仿真会话状态 |
| GET | `/v1/scenario/metadata` | 获取默认雄安示例场景配置 |

## 2. 场景生成

`POST /v1/scenario/generate` 依据经纬度调用 OSMnx，再调用 SUMO 工具生成 ZIP。请求约束见 `contracts/scenario_request.schema.json`。

```json
{"latitude": 38.9429, "longitude": 115.8977, "radius_m": 300, "duration_s": 3600}
```

成功时返回 `sumo_scenario.zip`，内含 `network.net.xml`、`traffic.rou.xml` 和 `scenario.sumocfg`。需要 `SUMO_HOME`、`osmnx` 与 OSM 网络访问。

## 3. 仿真会话

| 方法 | 路径 | 请求/参数 | 成功响应要点 |
|---|---|---|---|
| POST | `/v1/simulation/start` | `{"config_path":"scenario/tmp_treda0t.sumocfg"}` | `intersection_ids` |
| GET | `/v1/simulation/state` | 可选 `?intersection_id=<id>` | 时间、相位、排队、车道状态 |
| POST | `/v1/simulation/action` | `{"intersection_id":"id","phase":2,"duration_s":15}` | 已接受的相位 |
| POST | `/v1/simulation/step` | `{"steps":1}` | 当前仿真时间 |
| POST | `/v1/simulation/close` | 无 | 会话已关闭 |

控制动作见 `contracts/control_action.schema.json`，观测返回见 `contracts/observation.schema.json`。`phase` 必须为非负整数；实际可用相位由 SUMO 信号方案决定。

## 4. 调用示例

```powershell
curl.exe -X POST http://127.0.0.1:5000/v1/simulation/start -H "Content-Type: application/json" -d "{\"config_path\":\"scenario/tmp_treda0t.sumocfg\"}"
curl.exe http://127.0.0.1:5000/v1/simulation/state
curl.exe -X POST http://127.0.0.1:5000/v1/simulation/action -H "Content-Type: application/json" -d "{\"intersection_id\":\"<start响应中的ID>\",\"phase\":1}"
curl.exe -X POST http://127.0.0.1:5000/v1/simulation/step -H "Content-Type: application/json" -d "{\"steps\":5}"
```
