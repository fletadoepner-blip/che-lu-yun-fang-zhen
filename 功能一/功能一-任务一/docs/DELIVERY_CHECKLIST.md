# 交付与验收清单

## 可静态验证项

- [x] OSM 到 SUMO 场景生成入口和默认场景配置。
- [x] 路口状态读取、信号动作下发、仿真步进和会话关闭接口。
- [x] 场景请求、观测、控制动作 JSON Schema。
- [x] API 文档、字段字典、时序图和示例观测数据。
- [x] 交付完整性校验：`python scripts/verify_delivery.py`。

## 部署前由运行人确认

- [ ] Python 虚拟环境已安装 `requirements.txt`。
- [ ] `SUMO_HOME` 已配置，`sumo` 与 `netconvert` 可执行。
- [ ] 可访问 OpenStreetMap（仅在线生成场景时需要）。
- [ ] 复制/重命名已有示例场景文件后，`.sumocfg` 中引用的文件名一致。
- [ ] 运行 `/health`、`/v1/scenario/metadata`，并使用真实 SUMO 路口 ID 完成一次“状态-动作-步进-关闭”闭环。

## 本机基线情况（2026-08-28）

原始 `sim_api_service.py` 启动时缺少 `flask`，因此未进行 SUMO 动态仿真验证。该限制未被掩盖：服务会明确报告缺少依赖或 `SUMO_HOME`。补齐环境后按上述闭环进行验收，并将命令输出和截图作为 D01/D08 的运行证据。
