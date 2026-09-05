"""Summarize repeated CityFlow metrics into mean, sample standard deviation and CV."""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "重复试验结果"
OUT = ROOT / "最终主线_UGAT_TRANSYT_FRAP" / "任务3_重复实验波动统计.csv"
METRICS = ("average_travel_time_s", "estimated_delay_s", "throughput_est", "final_queue_proxy")


def main() -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for path in RAW.glob("repeat_*/*/*/metrics.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if rows:
            grouped[(path.parents[1].name, path.parents[0].name)].append(rows[-1])
    if not grouped:
        raise SystemExit(f"No repeated metrics found below {RAW}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    columns = ["method", "period", "runs"] + [item for metric in METRICS for item in (f"{metric}_mean", f"{metric}_std", f"{metric}_cv_pct")]
    with OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for (method, period), samples in sorted(grouped.items()):
            row: dict[str, str | int | float] = {"method": method, "period": period, "runs": len(samples)}
            for metric in METRICS:
                values = [float(sample[metric]) for sample in samples]
                mean = statistics.fmean(values)
                std = statistics.stdev(values) if len(values) > 1 else 0.0
                row[f"{metric}_mean"] = mean
                row[f"{metric}_std"] = std
                row[f"{metric}_cv_pct"] = std / mean * 100 if mean else 0.0
            writer.writerow(row)
    print(f"Wrote {len(grouped)} repeated-result summaries to {OUT}")


if __name__ == "__main__":
    main()
