# 高保真仿真验证平台模块开发与集成

本交付包将 CityFlow 仿真、信号控制算法、状态采集、结果落盘和离线可视化组织为统一平台。默认场景为雄安新区 20 路口路网。

## 交付内容

- `src/`：仿真运行器、算法适配器、UGAT+FRAP 控制器和离线仪表盘。
- `UGAT算法接口_标准化插件/`：可独立导入的算法插件契约、注册表和 UGAT 参考实现。
- `data/xiong_an_20/`：CityFlow 路网、早/中/晚高峰车流、拓扑和场景清单。
- `model/`：冻结 UGAT 主干及 FRAP 适配器权重。
- `configs/`：场景配置；`contracts/`：算法注册、输入输出示例及结果格式。
- `outputs/`：已验证的参考指标和轨迹；运行后会在此目录追加新结果。
- `docs/`：架构、模块边界、端到端流程、接口协议和验收清单。

## 环境

Python 3.10+。完整仿真需要 Linux/WSL/Docker 中可用的 CityFlow，以及 `pip install -r requirements.txt`。纯交付验收不依赖 CityFlow：

```powershell
python scripts/run_platform.py --mode demo
```

该命令校验算法适配器、算法注册信息、结果格式，并根据随包参考轨迹生成 `outputs/dashboard.html`。

## 完整闭环运行

```powershell
python scripts/run_platform.py --mode cityflow --algorithm max_pressure --period morning --steps 7500
python src/dashboard.py outputs/trace_max_pressure_morning.json --out outputs/dashboard.html
```

运行器会完成“场景导入 -> 状态采集 -> 算法选择 -> CityFlow 执行 -> 指标输出 -> 可视化”。`--algorithm` 可替换为 `fixed`、`max_pressure`、`actuated_pressure`、`transyt_style`、`ugat_frap` 或 `ugat_frap_transyt`，无需修改平台主循环。

算法插件接入方法、字段约束、异常行为和结果格式见 `docs/INTERFACE_PROTOCOL.md`；架构图和模块责任见 `docs/ARCHITECTURE.md`。
