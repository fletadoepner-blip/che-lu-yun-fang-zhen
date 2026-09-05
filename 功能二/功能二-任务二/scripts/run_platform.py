"""Unified platform entry point for portable acceptance and CityFlow execution."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def demo() -> None:
    from algorithms import MaxPressureAlgorithm

    registry = json.loads((ROOT / "contracts" / "algorithm_registry.json").read_text(encoding="utf-8"))
    state = json.loads((ROOT / "contracts" / "observation_example.json").read_text(encoding="utf-8"))["states"]
    import numpy as np
    actions = MaxPressureAlgorithm().choose(np.asarray(state, dtype=np.float32))
    if actions.shape != (2,) or not np.logical_and(actions >= 0, actions <= 7).all():
        raise RuntimeError("algorithm adapter returned invalid action(s)")
    with (ROOT / "outputs" / "metrics.csv").open(encoding="utf-8", newline="") as handle:
        fields = set(csv.DictReader(handle).fieldnames or [])
    required = set(json.loads((ROOT / "contracts" / "result_schema.json").read_text(encoding="utf-8"))["metrics_csv_required_columns"])
    if not required.issubset(fields):
        raise RuntimeError(f"metrics.csv misses fields: {sorted(required - fields)}")
    trace = ROOT / "outputs" / "trace_max_pressure_morning.json"
    subprocess.run([sys.executable, str(ROOT / "src" / "dashboard.py"), str(trace)], check=True)
    print(json.dumps({"status": "pass", "registered_algorithms": len(registry["algorithms"]), "sample_actions": actions.tolist()}, ensure_ascii=False))


def cityflow(args: argparse.Namespace) -> None:
    command = [sys.executable, str(ROOT / "src" / "run_cityflow.py"), "--algorithm", args.algorithm, "--period", args.period, "--steps", str(args.steps)]
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("demo", "cityflow"), default="demo")
    parser.add_argument("--algorithm", default="max_pressure")
    parser.add_argument("--period", choices=("morning", "midday", "evening"), default="morning")
    parser.add_argument("--steps", type=int, default=7500)
    args = parser.parse_args()
    demo() if args.mode == "demo" else cityflow(args)


if __name__ == "__main__":
    main()
