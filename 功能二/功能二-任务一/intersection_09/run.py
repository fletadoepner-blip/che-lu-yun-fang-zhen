# -*- coding: utf-8 -*-
"""独立路口仿真入口（纯 Python，无需 CityFlow C++ 引擎）。

用法示例：
    python run.py --algorithm max_pressure --steps 3600
    python run.py --algorithm fixed --steps 3600 --period midday

说明：
- 数据文件（roadnet.json / flow_*.json / cityflow.config.json）为标准 CityFlow
  格式，本脚本用内置轻量引擎仿真；装有 CityFlow 引擎（Linux/Docker）时，
  也可用同名 run_cityflow.py 运行原生版本。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from engine import Network, Simulator  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=("morning", "midday", "evening"), default="morning")
    ap.add_argument("--algorithm", choices=("fixed", "max_pressure"), default="max_pressure")
    ap.add_argument("--steps", type=int, default=3600)
    ap.add_argument("--dt", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=20260816)
    ap.add_argument("--report-every", type=int, default=600, help="0=关闭过程打印")
    args = ap.parse_args()

    net = Network(HERE, flow_file=f"flow_{args.period}.json")
    sim = Simulator(net, algorithm=args.algorithm, dt=args.dt,
                    max_sim_time=float(args.steps), seed=args.seed)
    report = args.report_every if args.report_every > 0 else None
    print(f"场景: 路口 {net.intersections.keys()}, 算法={args.algorithm}, "
          f"总需求={len(net.flow)}辆, 仿真时长={args.steps}s")
    metrics = sim.run(report_every=report)
    print("\n=== 仿真结果 ===")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    # 写入结果
    out = HERE / "outputs"
    out.mkdir(exist_ok=True)
    (out / f"metrics_{args.algorithm}_{args.period}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    if metrics["throughput"] < 0.999:
        print("[警告] 仍有车辆未完成，可增大 --steps。")
    else:
        print("[OK] 全部车辆已跑通。")


if __name__ == "__main__":
    main()
