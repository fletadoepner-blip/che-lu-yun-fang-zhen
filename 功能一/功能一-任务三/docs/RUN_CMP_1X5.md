# 1x5 Frozen UGAT + C-MP + CityFlow

## 说明

本项目使用用户提供的 `ugat1×5_best.pt`，冻结五个 UGAT 子网络的全部参数。C-MP 是基于本地 lane-link 车辆数和瞬时速度的确定性 Coordinated Max Pressure 控制器，不进行神经网络训练。`1x5_cmp_diagnostic_loss.png` 是 C-MP 压力分数与 UGAT Q 值的标准化 MSE 诊断图，不是训练 loss。

## 1. 从 PowerShell 启动 Docker

```powershell
docker run --rm -it --entrypoint /bin/bash -v "C:\Users\lauri\Desktop\1x5ugat+C-MP:/workspace/final" danielda1/ugat:latest
```

## 2. 进入运行目录

```bash
cd /DaRL/UGAT_Docker
```

## 3. 先做 100 步 smoke test

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 1 --test_steps 100 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x5_cmp_smoke
```

成功标准：日志打印五个 rank 的 `trainable_parameters=0`，并输出 `Final Travel Time`；宿主机 `logs/` 下生成 CSV、JSON 和 PNG。

## 4. 运行正式 C-MP 评测（9000 步）

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy cmp --beta 0.60 --alpha 0.60 --prefix 1x5_cmp_9000
```

## 5. 运行冻结 UGAT 对照（必须使用相同协议）

```bash
python /workspace/final/scripts/run_cmp_1x5.py --thread_num 4 --test_steps 9000 --seed 4444 --policy ugat --prefix 1x5_ugat_9000
```

## 6. 查看结果

在宿主机打开：

- `logs/1x5_cmp_simulation_metrics.csv`
- `logs/1x5_cmp_simulation_metrics.png`
- `logs/1x5_cmp_diagnostic_loss.png`
- `logs/1x5_cmp_latest_metrics.json`

只在同一 `test_steps`、seed、CityFlow 配置和统计方式下比较 C-MP 与 UGAT。不要将论文 AIMSUN 结果或其他流量协议的 Travel Time 直接与本项目结果比较。
