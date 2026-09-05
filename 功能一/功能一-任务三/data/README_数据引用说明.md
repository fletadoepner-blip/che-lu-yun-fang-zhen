# 数据引用说明（data/xiong_an_20）

## 本目录是什么

`data/xiong_an_20/` 是雄安容东片区 20 路口 CityFlow 场景数据（roadnet、flow、信号配时、拓扑、清单）。为避免在同一工作区重复存放约 97 MB 流量文件，本交付**引用功能二·任务二同一份数据目录**：

- 本机（Windows）当前通过 **NTFS junction** 指向：
  `D:\挑战杯揭榜挂帅2026\功能二-任务二\任务2_平台模块开发与集成\data\xiong_an_20`
- 因此在本工作区内，`src/validate_scenario.py`、`src/run_cityflow.py` 等可直接读取，无需复制。

## 文件清单（与功能二-任务二完全一致）

| 文件 | 用途 |
|---|---|
| `roadnet.json` | 20 控制节点 CityFlow 路网 |
| `flow_morning.json` / `flow_midday.json` / `flow_evening.json` | 三时段逐车需求（77,749 / 54,864 / 87,051 辆） |
| `source_signal_plans.json` | 原始 Excel 配时（审计材料，不作为训练标签） |
| `topology.json` | 4×5 拓扑与路口命名 |
| `manifest.json` / `excel_audit.json` | 路口清单与 20/20 工作簿核验记录 |
| `cityflow.config.json` | CityFlow 引擎配置模板 |

## 独立打包/外发时怎么做

压缩包不会自动跟随 junction，外发前必须把数据变成真实文件：

```powershell
# 方式一：删除 junction 后整目录复制（推荐，一次性变为独立数据）
Remove-Item data\xiong_an_20 -Force
Copy-Item "D:\挑战杯揭榜挂帅2026\功能二-任务二\任务2_平台模块开发与集成\data\xiong_an_20" data\xiong_an_20 -Recurse

# 方式二：运行配套脚本（自动检测 junction 并转为复制）
powershell -ExecutionPolicy Bypass -File scripts\make_data_standalone.ps1
```

复制完成后重新执行 `python src/validate_scenario.py` 确认 `morning=77749, midday=54864, evening=87051`。

## 重要

- 本目录内容与功能二·任务二共享，**不要单独修改**；如需更新数据，请在功能二·任务二的数据目录修改后同步。
- 该场景是依据高德截图/地标整理的近似拓扑（4×5 微弧网络），不是测绘级 OSM/netedit 车道模型；严格车道级验证需补充合规 OSM 数据（见 `docs/MAP_AND_GEOMETRY.md`）。
- **Docker 构建注意**：`docker build .` 的构建上下文不一定跟随 NTFS junction。执行 `docker build` 前建议先运行 `scripts/make_data_standalone.ps1` 将数据转为真实文件（该脚本会自动检测 junction 并复制），否则镜像构建阶段的 `validate_scenario.py` 可能因读不到数据而失败。
