# -*- coding: utf-8 -*-
"""原生 CityFlow 引擎运行入口（需 Linux/Docker 环境已安装 cityflow）。

数据文件为标准 CityFlow 格式，本脚本在装有 CityFlow 引擎的环境下运行：

    python run_cityflow.py --algorithm max_pressure --steps 7600

不依赖本项目的 torch / UGAT 模型；只提供固定相位与最大压力两种控制，
以验证单路口场景在原生引擎下可跑通。
"""
from __future__ import annotations

import argparse
import json
import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent


class FixedTimeAlgorithm:
    name = "fixed_time"

    def __init__(self, count: int, hold_decisions: int = 3, phase_offset: int = 0):
        self.count = count
        self.step = 0
        self.hold = hold_decisions
        self.offset = phase_offset

    def choose(self, states: np.ndarray) -> np.ndarray:
        action = np.full(self.count, (self.offset + self.step // self.hold) % 8, dtype=np.int64)
        self.step += 1
        return action


class MaxPressureAlgorithm:
    name = "max_pressure"
    ACTION_LANES = ((1, 4), (7, 10), (0, 3), (6, 9), (0, 1), (3, 4), (9, 10), (6, 7))

    def choose(self, states: np.ndarray) -> np.ndarray:
        demand = states[:, :12]
        score = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        return score.argmax(axis=1).astype(np.int64)


def collect_state(engine, roadnet: dict) -> np.ndarray:
    """聚合单路口 12 个固定流向槽位：W/E/N/S x (左/直行/右)。"""
    CONTROL_GROUP = {"W": "W", "E": "E", "N": "N", "S": "S",
                     "NW": "N", "NE": "N", "SW": "S", "SE": "S"}
    inter = next(i for i in roadnet["intersections"] if not i.get("virtual"))
    groups = {d: [] for d in "WENS"}
    for rid in inter["roads"]:
        road = next(r for r in roadnet["roads"] if r["id"] == rid)
        if road["endIntersection"] != inter["id"]:
            continue
        if rid.startswith("feed_"):
            groups[CONTROL_GROUP[rid.rsplit("_", 1)[1]]].append(rid)
        elif rid.startswith("link_"):
            dep = rid.split("_")[2]
            groups[CONTROL_GROUP[{"W": "E", "E": "W", "N": "S", "S": "N",
                                  "NW": "SE", "NE": "SW", "SW": "NE", "SE": "NW"}[dep]]].append(rid)
    values = []
    for d in "WENS":
        left = sum(int(engine.get_lane_vehicle_count().get(f"{rid}_0", 0)) for rid in groups[d])
        sr = sum(int(engine.get_lane_vehicle_count().get(f"{rid}_1", 0)) for rid in groups[d])
        values += [left, sr, sr]
    return np.asarray([values], dtype=np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=("morning", "midday", "evening"), default="morning")
    ap.add_argument("--algorithm", choices=("fixed", "max_pressure"), default="max_pressure")
    ap.add_argument("--steps", type=int, default=7600)
    ap.add_argument("--decision-interval", type=int, default=10)
    ap.add_argument("--threads", type=int, default=1)
    args = ap.parse_args()

    try:
        import cityflow
    except ImportError as exc:
        raise SystemExit("CityFlow 未安装。请使用 Docker 或 Linux 环境安装 cityflow。") from exc

    config = json.loads((HERE / "cityflow.config.json").read_text(encoding="utf-8"))
    config["flowFile"] = f"flow_{args.period}.json"
    config["dir"] = str(HERE.resolve()).replace("\\", "/") + "/"
    runtime = HERE / f"runtime_{args.period}.json"
    runtime.write_text(json.dumps(config, indent=2), encoding="utf-8")

    engine = cityflow.Engine(str(runtime), thread_num=args.threads)
    roadnet = json.loads((HERE / "roadnet.json").read_text(encoding="utf-8"))
    flow = json.loads((HERE / config["flowFile"]).read_text(encoding="utf-8"))
    departures = sorted(item["startTime"] for item in flow)

    if args.algorithm == "fixed":
        controller = FixedTimeAlgorithm(1)
    else:
        controller = MaxPressureAlgorithm()

    jid = next(i["id"] for i in roadnet["intersections"] if not i.get("virtual"))
    actions = np.zeros(1, dtype=np.int64)
    for tick in range(args.steps):
        if tick % args.decision_interval == 0:
            state = collect_state(engine, roadnet)
            actions = controller.choose(state)
            engine.set_tl_phase(jid, int(actions[0]) + 1)
        engine.next_step()

    metrics = {
        "algorithm": controller.name,
        "period": args.period,
        "steps": args.steps,
        "total_demand": len(departures),
        "active_vehicles": int(engine.get_vehicle_count()),
        "average_travel_time_s": round(float(engine.get_average_travel_time()), 3),
    }
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
