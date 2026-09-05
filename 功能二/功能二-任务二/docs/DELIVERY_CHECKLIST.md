# 提交材料核查单

| 验收项 | 对应材料 | 核查结果 |
| --- | --- | --- |
| 仿真引擎集成 | `src/run_cityflow.py`、`data/xiong_an_20/cityflow.config.json` | 已具备 |
| 算法统一替换 | `src/algorithms.py`、`contracts/algorithm_registry.json`、UGAT 插件包 | 已具备 |
| 数据采集 | `collect_state`、`vehicle_snapshot`、参考轨迹 | 已具备 |
| 可视化 | `src/dashboard.py`、`outputs/trace_max_pressure_morning.json` | 已具备 |
| 统一运行入口 | `scripts/run_platform.py` | 已补齐 |
| 异常处理 | 运行器、插件模型和协议说明 | 已具备并已说明 |
| 模块配置与接口协议 | `configs/`、`contracts/`、`docs/INTERFACE_PROTOCOL.md` | 已补齐 |
| 示例输入输出 | `contracts/observation_example.json`、`outputs/` | 已补齐 |
| 架构图、模块边界、流程图 | `docs/ARCHITECTURE.md` | 已补齐 |
| 端到端闭环验收 | `README.md` 命令与 `scripts/run_platform.py --mode demo` | 已补齐 |

## 提交前执行

```powershell
python scripts/run_platform.py --mode demo
python -m compileall -q src scripts UGAT算法接口_标准化插件
```

完整 CityFlow 环境可额外执行 README 中的 `--mode cityflow` 命令。
