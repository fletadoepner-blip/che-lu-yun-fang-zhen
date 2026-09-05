# 架构与模块边界

## 目标

功能一·任务一把“雄安新区目标区域的 OSM 路网”和“控制算法可消费的仿真状态”连接起来。接口层不实现具体优化算法，仅保证算法可在同一时间步读取观测、提交动作并推进仿真。

```text
OSM 坐标/半径
     │ POST /v1/scenario/generate
     ▼
OSMnx 下载 ──> netconvert ──> SUMO 路网 + 车流 + .sumocfg ZIP
                                      │
                                      ▼
控制算法 ── GET /state ── SUMO/TraCI ── POST /action
    │                                  │
    └──────── POST /step <─────────────┘
```

## 模块责任

| 模块 | 责任 | 输入 | 输出 |
|---|---|---|---|
| `src/service.py` | HTTP 边界、参数校验、状态接口 | JSON / query | JSON / ZIP |
| `_build_scenario` | OSM 到 SUMO 场景构建 | 坐标、范围、时长 | 路网、路线、配置压缩包 |
| TraCI 适配段 | 启动、观测、动作、步进、关闭 | SUMO 配置、动作 | 路口状态 |
| `contracts/` | 固定字段、类型与范围 | - | 可校验 Schema |
| `data/xiong_an_sample/` | 字段示例，供联调使用 | - | 示例 JSON |

## 运行边界

- OSM 下载、SUMO 启动均属于外部依赖；服务会返回可诊断错误，不伪造场景或仿真结果。
- 路口 ID 以 `POST /v1/simulation/start` 的响应为准，不应在算法端硬编码。
- 服务为单进程联调实现，同一时刻仅允许一个 SUMO 会话；生产部署应增加会话隔离、鉴权、限流和审计日志。
