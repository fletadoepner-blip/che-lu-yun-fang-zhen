# 雄安 20 路口 CityFlow 复现包

本目录是功能二任务一的完整联动场景，使用官方 CityFlow 源码（固定提交 `81ee0f47659ca66177a71f81676691c58ee89184`）及其 `pybind11`、`rapidjson` 子模块，源码位于 `third_party/CityFlow`。场景数据来自雄安新区 20 份路口 Excel，未改写原始流量审计结果。

运行环境固定为 Linux x86_64 Docker 和 Python 3.10。该 CityFlow 固定版本内置 pybind11 2.3.0，不兼容 Python 3.11 及以上版本。

## 内容与验收接口

- `data/xiong_an_20/roadnet.json`：20 个受控路口、虚拟边界节点和完整 roadLinks。
- `data/xiong_an_20/flow_{morning,midday,evening}.json`：多时段输入；`flow_midday_pressure{10,20,30,120}.json` 为压力扰动输入。
- `topology.json`、`source_signal_plans.json`、`manifest.json`、`excel_audit.json`：拓扑、信号方案、路口清单及来源审计。
- `src/build_xiong_an_20.py`：从 20 份 Excel 导入、转换路网和流量的可复现脚本；`src/validate_scenario.py`：路网、流量、信号和 20 份 Excel 守恒校验。
- `src/run_cityflow.py`：CityFlow 启动及控制器运行入口；`src/check_cityflow.py`：引擎导入检查。
- `Dockerfile`、`docker-compose.yml`、`run_cityflow.ps1`：从本地 third_party 源码编译并运行，避免使用未锁定的系统 CityFlow。

## 运行

在本目录执行：

```powershell
python .\src\validate_scenario.py
docker compose run --rm cityflow-xiong-an-20
```

或：

```powershell
.\run_cityflow.ps1 -Period morning -Steps 7500 -Algorithm max_pressure
```

无外网时，使用随包提供的已验证 Linux x86_64 镜像：

```powershell
.\run_offline.ps1 -Period morning -Steps 7500 -Algorithm max_pressure
```

该脚本首次自动执行 `docker load`；镜像 SHA-256 记录于 `docker/SHA256SUMS.txt`。

输出写入 `outputs/metrics.csv`、`outputs/trace_max_pressure_morning.json`。可将 `Period` 改为 `midday` 或 `evening`；压力流量可直接运行：

```powershell
docker compose run --rm cityflow-xiong-an-20 --period midday --flow-file flow_midday_pressure30.json --algorithm max_pressure --steps 7500 --threads 1
```

## 本机检查结果

`validate_scenario.py` 已通过：20 个受控路口、294 条道路；早/平/晚高峰车辆数分别为 77,749、54,864、87,051，20/20 份 Excel 审计一致。若本机未安装 Docker 或编译工具，原生 CityFlow 动态运行需在 Docker/Linux 环境执行；`check_cityflow.py` 会明确报告缺少引擎，而不会伪造结果。
