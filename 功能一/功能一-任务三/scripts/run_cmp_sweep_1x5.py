"""Run reproducible C-MP parameter/seed evaluations and summarize stable settings.

Run inside the UGAT Docker container after mounting this project at
/workspace/final. C-MP has no gradient training; this is the appropriate
replacement for changing learning rate or batch size.
"""
import argparse
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


def parse_pairs(value):
    try:
        pairs = []
        for item in value.split(","):
            beta, alpha = item.split(":")
            beta, alpha = float(beta), float(alpha)
            if beta < 0 or not 0 <= alpha <= 1:
                raise ValueError
            pairs.append((beta, alpha))
        return pairs
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pairs must look like 0.40:0.40,0.60:0.60") from exc


def main():
    parser = argparse.ArgumentParser(description="C-MP grid search with repeated CityFlow seeds")
    parser.add_argument("--steps", type=int, default=9000)
    parser.add_argument("--seeds", default="4444,4445,4446")
    parser.add_argument("--pairs", type=parse_pairs, default="0.40:0.40,0.60:0.60,0.80:0.60")
    parser.add_argument("--thread_num", type=int, default=4)
    args = parser.parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if not seeds:
        parser.error("at least one seed is required")
    started = datetime.now().isoformat(timespec="seconds")
    runner = "/workspace/final/scripts/run_cmp_1x5.py"
    for beta, alpha in args.pairs:
        for seed in seeds:
            prefix = f"cmp_b{beta:.2f}_a{alpha:.2f}_s{seed}".replace(".", "")
            command = [sys.executable, runner, "--thread_num", str(args.thread_num), "--test_steps", str(args.steps), "--seed", str(seed), "--policy", "cmp", "--beta", str(beta), "--alpha", str(alpha), "--prefix", prefix]
            print("running:", " ".join(command), flush=True)
            subprocess.run(command, check=True)
    metrics_path = Path("/workspace/final/logs/1x5_cmp_simulation_metrics.csv")
    with metrics_path.open(encoding="utf-8") as handle:
        records = [row for row in csv.DictReader(handle) if row["timestamp"] >= started and row["policy"] == "cmp" and int(row["test_steps"]) == args.steps]
    groups = {}
    for row in records:
        groups.setdefault((row["beta"], row["alpha"]), []).append(row)
    summary_path = metrics_path.with_name("1x5_cmp_sweep_summary.csv")
    fields = ["beta", "alpha", "runs", "travel_time_mean", "travel_time_std", "queue_mean", "delay_ratio_mean", "throughput_mean", "reward_mean"]
    summaries = []
    for (beta, alpha), rows in sorted(groups.items()):
        metric = lambda key: np.asarray([float(row[key]) for row in rows], dtype=float)
        summaries.append({"beta": beta, "alpha": alpha, "runs": len(rows), "travel_time_mean": metric("travel_time").mean(), "travel_time_std": metric("travel_time").std(ddof=0), "queue_mean": metric("queue").mean(), "delay_ratio_mean": metric("delay_ratio_apx").mean(), "throughput_mean": metric("throughput").mean(), "reward_mean": metric("rewards").mean()})
    summaries.sort(key=lambda row: (row["travel_time_mean"], row["queue_mean"], -row["throughput_mean"]))
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(summaries)
    print("sweep_summary=" + str(summary_path), flush=True)
    for row in summaries:
        print(f"ranked beta={row['beta']} alpha={row['alpha']} runs={row['runs']} travel_time_mean={row['travel_time_mean']:.4f} std={row['travel_time_std']:.4f} queue_mean={row['queue_mean']:.4f} throughput_mean={row['throughput_mean']:.1f}", flush=True)


if __name__ == "__main__":
    main()
