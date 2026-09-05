# 接口协议、输入输出维度与配置一致性

> 这份文档把"模型能加载、输入输出维度跟配置对得上"这条验收标准钉死，避免出现权重、配置、代码三者各说各话的情况。

## 1. 各模型的输入输出维度

| 模型 | 输入 | 输出 | 一致性检查 |
|---|---|---|---|
| FrozenUGAT（20路口/4×4） | `[batch, 20]` float32 | `[batch, 8]` | `torch.load` 后 key 集合必须等于 `dense_1/dense_2/dense_3` 的 state_dict，否则直接 `RuntimeError` |
| FRAPAdapter | `[batch, 20]`（内部重排成 `[12车道, 8相位]`） | `[batch, 8]` | 维度校验 `state.ndim==2 and state.shape[1]==20` |
| UGATFRAPController | `[batch, 20]` | `[batch]` int64（0..7） | `assert_frozen()` 检查 UGAT 参数 `requires_grad=False` |
| 1×3/1×5 UGAT（rank0..4） | `[8,6,8,12,12]` 每路口 | `[2,1,2,4,4]` 每 rank | 分层加载，参数合计 3393，全部冻结 |

配置里的权重路径（`configs/xiong_an_20.yaml` 的 `model.checkpoint`、`model.adapter_state`）必须指向 `model/` 下真实存在的文件。

## 2. 动作映射

- 算法动作是 `0..7`；平台内部 `set_tl_phase(f"j_{node:02d}", int(action)+1)` 映射到 CityFlow 相位 `1..8`。
- 动作 `0` 永远是 3 秒黄灯/清空相位，不允许算法长期占用。
- MaxPressure 基线的车道对（`src/algorithms.py::ACTION_LANES`）是 `((1,3),(5,7),(0,2),(4,6),(0,1),(2,3),(6,7),(4,5))`，索引对应状态前 8 维 `[WL,WT,EL,ET,NL,NT,SL,ST]`。

## 3. 观测字段字典

| 字段 | 类型/范围 | 含义 |
|---|---|---|
| `lane_demand[0..11]` | int ≥0 | 12 车道组车辆数：`[W左,W直右,W直右, E左,E直右,E直右, N左,N直右,N直右, S左,S直右,S直右]` |
| `phase_one_hot[0..7]` | 0/1 | 8 个相位里当前激活的那个 |
| `active_vehicles` | int ≥0 | 在网车辆数（评估输出） |
| `queue_proxy` | int ≥0 | 排队代理量（评估输出） |

## 4. 公平对比的规矩

1. 同一场景、同一 `period`、同一 `steps`、同一 `threads`、同一随机种子；
2. 基线和算法用同一份流量文件、同一个统计口径；
3. 重复运行取均值、标准差（至少 3 个 seed）才能下统计结论；
4. `delay_ratio_apx` 和 `delay_type=real` 的累计延迟**不能混用**；
5. 20 路口主算法和基线的正式结论，要在斜向进口修正后的新路网上重新做完对比再下（见 `docs/ABLATION.md` 第 5 节）。

## 5. 异常和约束

1. 缺 `cityflow` 引擎时运行器直接报错退出，不伪造结果。
2. 模型 key 不匹配、维度不符、UGAT 没冻结，分别抛 `RuntimeError`/`ValueError`。
3. 实验都在 `finally` 语义下关掉 CityFlow 引擎（`run_cityflow.py` 用进程级引擎生命周期）。
4. 数据目录找不到时，先看 `data/README_数据引用说明.md`，把数据链接或复制好再跑。
