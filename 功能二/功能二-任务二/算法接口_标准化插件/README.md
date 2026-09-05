# UGAT 参数暴露与算法接口

本目录以 `UGAT/official_ugat_best.pt` 为冻结基座，提供面向外部算法的稳定边界。

## 快速使用

```python
from pathlib import Path
from ugat_interface import UGATAlgorithm, UGATConfig

root = Path(r"C:\Users\lauri\Desktop\1x5\UGAT_frozen")
config = UGATConfig.from_yaml(root / "UGAT/configs/official/official_ugat.yml")
agent = UGATAlgorithm(root / "UGAT/official_ugat_best.pt", config)
action = agent.choose_action([0.0] * 16)
q_values = agent.q_values([[0.0] * 16, [1.0] * 16])
```

输入可以是 `[16]` 或 `[N, 16]` 的有限数值；输出动作是 `0..7`，批量输入返回 `int64[N]`。`explore=True` 才启用 epsilon 随机动作。官方主干权重始终冻结，若提供 `adapter_checkpoint`，只加载 adapter 权重。

未提供 adapter checkpoint 时，adapter 初始化为零残差，因此输出与官方冻结基座一致。

## 接入新算法

实现 `choose_action`, `update`, `reset` 三个方法后注册：

```python
from ugat_interface import registry
registry.register("my_algorithm", MyAlgorithm)
agent = registry.create("my_algorithm", **kwargs)
```

## 验证

在已安装 PyTorch 的环境运行：

```powershell
python verify_interface.py
```

验证脚本会自动处理部分 Anaconda 环境中的 Intel OpenMP 重复库提示。
