"""Reject incomplete or regressive SUMO experiment results before submission."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
RESULTS = PROJECT / "results"
METRICS = (
    "mean_travel_time_s",
    "mean_waiting_time_s",
    "mean_time_loss_s",
    "mean_queue_vehicles",
)


def load(strategy: str) -> dict:
    path = RESULTS / f"metrics_{strategy}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run run_experiment.py --mode both first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [name for name in ("completed_vehicles", *METRICS) if name not in data]
    if missing:
        raise ValueError(f"{path.name} misses required fields: {missing}")
    if int(data["completed_vehicles"]) <= 0:
        raise ValueError(f"{path.name} has no completed vehicles")
    for name in METRICS:
        if float(data[name]) < 0:
            raise ValueError(f"{path.name} has invalid negative {name}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-travel-improvement", type=float, default=10.0)
    args = parser.parse_args()
    fixed, adaptive = load("fixed"), load("adaptive")
    if adaptive["completed_vehicles"] < fixed["completed_vehicles"]:
        raise SystemExit("FAILED: adaptive control completed fewer vehicles than fixed-time control")
    if fixed["mean_waiting_time_s"] <= 0 or adaptive["mean_waiting_time_s"] <= 0:
        raise SystemExit("FAILED: waiting-time metric is zero; inspect tripinfo before submission")
    improvements = {
        metric: (fixed[metric] - adaptive[metric]) / fixed[metric] * 100
        for metric in METRICS
    }
    travel_improvement = improvements["mean_travel_time_s"]
    if travel_improvement < args.min_travel_improvement:
        raise SystemExit(
            f"FAILED: travel-time improvement {travel_improvement:.2f}% is below "
            f"required {args.min_travel_improvement:.2f}%"
        )
    print("PASS: result acceptance checks")
    print(f"completed vehicles: {fixed['completed_vehicles']} -> {adaptive['completed_vehicles']}")
    for metric in METRICS:
        print(f"{metric}: {fixed[metric]:.2f} -> {adaptive[metric]:.2f}; improvement={improvements[metric]:.2f}%")


if __name__ == "__main__":
    main()
