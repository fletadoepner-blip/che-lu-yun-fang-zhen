# 架构与模块边界

## 目标

功能一·任务三要把"智能交通决策模型"（UGAT/C-MP/FRAP）落成可加载、可推理、可对比的交付：权重和配置分开、训练和评测入口分开、第三方引擎和自研代码分开，让评委照着 README 就能复现。

```text
┌────────────────────── 数据层 ──────────────────────┐
│ data/xiong_an_20（引用功能二-任务二）                  │
│ roadnet.json / flow_{morning,midday,evening}.json   │
│ source_signal_plans.json / topology.json             │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌────────────────────── 仿真层 ──────────────────────┐
│ third_party/CityFlow（固定提交 81ee0f47，源码编译）    │
│ src/run_cityflow.py（多线程引擎 + 状态采集）           │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌────────────────────── 算法适配层 ────────────────────┐
│ src/algorithms.py::SignalAlgorithm（统一契约）         │
│ ├─ FixedTimeAlgorithm / MaxPressureAlgorithm（基线）  │
│ └─ UGATFRAPController（冻结UGAT + FRAP，src/ugat_frap.py）│
│ 1×3/1×5 / 4×4：scripts/ugat_cmp_1x5.py、ugat_farp_4x4_model.py│
└──────────────────────┬──────────────────────────────┘
                       ▼
┌────────────────────── 采集与展示层 ───────────────────┐
│ outputs/metrics.csv / trace_*.json / dashboard.html    │
│ scripts/run_and_show.ps1（Windows 动态窗口）           │
└───────────────────────────────────────────────────────┘
```

## 各部分干什么

| 模块 | 责任 | 输入 | 输出 |
|---|---|---|---|
| `src/algorithms.py` | 算法统一契约（SignalAlgorithm） | `[N,12]` 状态数组 | `[N]` 相位动作 |
| `src/ugat_frap.py` | 冻结 UGAT 基座 + FRAP 适配器 + 融合 | `[batch,20]` | `[batch,8]` Q 值/动作 |
| `src/run_cityflow.py` | CityFlow 评测入口、状态采集、指标输出 | period/algorithm/steps | metrics.csv、trace JSON |
| `src/train_adapter.py` | 只训练 FRAP 适配器 | CityFlow 回合 | `model/frap_adapter.pt` |
| `src/validate_scenario.py` | 不依赖引擎的静态场景校验 | data JSON | PASS/FAIL |
| `configs/` | 模型与场景参数（seed、相位对、权重路径） | - | YAML |
| `contracts/` | 模型注册表、状态/动作 Schema | - | JSON |
| `model/` | 权重与版本说明 | - | .pt + 说明 |

## 第三方与自研的边界

- `third_party/CityFlow/`：官方 CityFlow 源码（固定提交 `81ee0f47659ca66177a71f81676691c58ee89184`），Docker 构建阶段编译，许可证见它自己的 `LICENSE.txt`；**不改它的源码**，只在上面做适配。
- 自研代码：`src/`、`scripts/`、`configs/`、`docs/` 里非 third_party 的部分。
- 1×3/1×5、4×4 工程依赖官方镜像 `danielda1/ugat:latest` 里的 `/DaRL/UGAT_Docker` 框架，只把本包脚本挂载进容器跑。

## 运行边界（几条实话）

- 20 路口平台：`import cityflow` 失败就明确报错退出，不伪造仿真结果；动态窗口是 CityFlow 车辆位置的实时示意图，不是高精度地图渲染。
- 数据：`data/xiong_an_20` 是 junction 引用（见 `data/README_数据引用说明.md`），独立打包前要按说明复制成真实文件。
- 结论边界：`docs/ABLATION.md` 第 5 节写清楚了，20 路口主算法还没做多种子基线对比，不宣称性能提升；1×3 最终结果待补跑。
