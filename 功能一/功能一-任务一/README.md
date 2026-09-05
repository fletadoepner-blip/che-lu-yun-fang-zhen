# 功能一·任务一：场景建模与数据接口设计

本交付包面向雄安新区城市窄路与多路口协同管控场景，提供从 OSM 路网到 SUMO 场景的生成入口，以及供控制算法读取状态、下发信号动作、推进仿真的统一接口。

## 交付结构

- `src/`：可运行的 Flask 服务、SUMO 适配器及输入校验。
- `configs/`：默认场景与服务参数。
- `contracts/`：请求、观测和控制动作 JSON Schema。
- `data/xiong_an_sample/`：接口字段示例与路口登记表；不作为真实实验数据。
- `docs/`：API、架构、接口协议和验收清单。
- `scripts/verify_delivery.py`：不依赖 SUMO 的交付完整性校验。
- `scenario/`：原始接口生成的 SUMO 示例场景，保留其临时文件名以保持配置引用一致。

## 安装与运行

Python 3.10+，并安装 SUMO（将 `SUMO_HOME` 指向其安装目录）。Windows PowerShell 示例：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SUMO_HOME = 'C:\Program Files (x86)\Eclipse\Sumo'
python sim_api_service.py
```

服务默认监听 `http://127.0.0.1:5000`。运行依赖及排错见 `docs/DELIVERY_CHECKLIST.md`。

## 五分钟验收

```powershell
python scripts/verify_delivery.py
curl http://127.0.0.1:5000/health
curl "http://127.0.0.1:5000/v1/scenario/metadata"
```

如已正确安装 SUMO，可将 `configs/default_scenario.json` 中的 `config_path` 传给 `POST /v1/simulation/start`。首次启动前应复制或重命名 `scenario/` 内三个文件，并同步更新 `.sumocfg` 内的文件名；`/v1/scenario/generate` 输出的 ZIP 已使用规范文件名。

接口字段、时序和可调用示例见 `docs/API.md` 与 `docs/INTERFACE_PROTOCOL.md`。
