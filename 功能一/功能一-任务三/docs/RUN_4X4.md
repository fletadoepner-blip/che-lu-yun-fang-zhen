# 4x4 UGAT + FRAP 复现说明

## 容器启动

```powershell
docker run --rm -it --entrypoint /bin/bash -v "C:\Users\lauri\Desktop\4x4ugat+frap:/workspace/final" danielda1/ugat:latest
```

## 容器内准备

```bash
cp /workspace/final/configs/farp4x4.yml /DaRL/UGAT_Docker/configs/tsc/farp4x4.yml
cd /DaRL/UGAT_Docker
```

## 100 步接口验证

```bash
python /workspace/final/scripts/run_farp_4x4.py --thread_num 1 --test_steps 100 --prefix 4x4_smoke
```

## 3600 步正式评测

```bash
python /workspace/final/scripts/run_farp_4x4.py --thread_num 4 --test_steps 3600 --prefix 4x4_formal
```

## FRAP 适配器训练与恢复

```bash
python /workspace/final/scripts/train_4x4_adapter.py --epochs 10 --state /workspace/final/logs/4x4_farp_adapter.pt
python /workspace/final/scripts/train_4x4_adapter.py --resume --epochs 10 --state /workspace/final/logs/4x4_farp_adapter.pt
```

每次仿真将追加 `logs/4x4_simulation_metrics.csv` 并更新 JSON 与 PNG 趋势图。
