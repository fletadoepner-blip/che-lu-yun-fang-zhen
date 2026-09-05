"""Recompute Task 3 summary tables and figures from the archived raw outputs.

This script intentionally reads only metrics.csv and trace_*.json below raw_outputs.
It does not contain hand-entered experimental measurements.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "最终主线原始指标与轨迹" / "outputs" / "ablation_transyt"
OUT = ROOT / "最终主线_UGAT_TRANSYT_FRAP"
PERIODS = [("morning", "早高峰"), ("midday", "平峰"), ("evening", "晚高峰")]
METHODS = [
    ("fixed", "固定配时"),
    ("transyt", "TRANSYT-only"),
    ("ugat_frap", "UGAT+FRAP（无TRANSYT）"),
    ("ugat_transyt", "UGAT+TRANSYT（去FRAP）"),
    ("frap_transyt", "FRAP+TRANSYT（去UGAT）"),
    ("ugat_frap_transyt", "完整 UGAT+FRAP+TRANSYT"),
]
CANONICAL = [
    "algorithm", "period", "steps", "wall_seconds", "steps_per_second",
    "total_demand", "scheduled_vehicles", "completed_vehicles_est", "throughput_est",
    "final_active_vehicles", "final_queue_proxy", "average_travel_time_s",
    "estimated_delay_s", "freeflow_mean_s", "coordination_decisions",
    "frap_override_count", "frap_override_rate", "transyt_frap_agreement_rate",
    "coordination_override_ratio", "coordination_overload_ratio", "coordination_minimum_gain",
]


def read_row(method: str, period: str) -> dict[str, float | str]:
    folder = RAW / method / period
    with (folder / "metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise RuntimeError(f"empty metrics: {folder / 'metrics.csv'}")
    values = dict(zip(rows[0], rows[1])) if rows[0][0] == "algorithm" else dict(zip(CANONICAL, rows[-1]))
    trace_file = next(folder.glob("trace_*.json"))
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    queues = [float(item.get("queue_proxy", 0)) for item in trace]
    result: dict[str, float | str] = {"method_key": method, "method": dict(METHODS)[method], "period": period, "period_label": dict(PERIODS)[period]}
    for key, value in values.items():
        try:
            result[key] = float(value)
        except ValueError:
            result[key] = value
    result["mean_queue_proxy"] = sum(queues) / len(queues) if queues else 0.0
    result["max_queue_proxy"] = max(queues, default=0.0)
    return result


def improvement(baseline: float, value: float, higher_is_better: bool = False) -> float:
    return ((value - baseline) if higher_is_better else (baseline - value)) / baseline * 100.0


def write_csv(rows: list[dict[str, float | str]]) -> None:
    columns = [
        "period", "period_label", "method_key", "method", "average_travel_time_s",
        "estimated_delay_s", "mean_queue_proxy", "max_queue_proxy", "throughput_est",
        "completed_vehicles_est", "tt_improvement_vs_fixed_pct",
        "delay_improvement_vs_fixed_pct", "queue_improvement_vs_fixed_pct",
    ]
    with (OUT / "任务3_多指标复算汇总.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in columns} for row in rows)


def plot(rows: list[dict[str, float | str]]) -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    colors = ["#65737e", "#2878b5", "#32a852", "#e58c29", "#8f5aa8", "#c9413a"]
    for metric, label in [("average_travel_time_s", "平均旅行时间 (s)"), ("estimated_delay_s", "估计延误 (s)"), ("mean_queue_proxy", "平均队列代理")]:
        fig, axis = plt.subplots(figsize=(10.5, 5.2))
        x = list(range(len(PERIODS)))
        width = 0.12
        for index, (method, name) in enumerate(METHODS):
            values = [float(next(row[metric] for row in rows if row["method_key"] == method and row["period"] == period)) for period, _ in PERIODS]
            axis.bar([item + (index - 2.5) * width for item in x], values, width, label=name, color=colors[index])
        axis.set_xticks(x, [label for _, label in PERIODS])
        axis.set_ylabel(label)
        axis.set_title(f"雄安新区20路口消融实验：{label}")
        axis.grid(axis="y", alpha=0.25)
        axis.legend(ncol=3, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12))
        fig.tight_layout()
        fig.savefig(OUT / f"任务3_{metric}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [read_row(method, period) for method, _ in METHODS for period, _ in PERIODS]
    for row in rows:
        fixed = next(item for item in rows if item["method_key"] == "fixed" and item["period"] == row["period"])
        row["tt_improvement_vs_fixed_pct"] = improvement(float(fixed["average_travel_time_s"]), float(row["average_travel_time_s"]))
        row["delay_improvement_vs_fixed_pct"] = improvement(float(fixed["estimated_delay_s"]), float(row["estimated_delay_s"]))
        row["queue_improvement_vs_fixed_pct"] = improvement(float(fixed["mean_queue_proxy"]), float(row["mean_queue_proxy"]))
    write_csv(rows)
    plot(rows)
    (OUT / "任务3_复算清单.json").write_text(json.dumps({"methods": [key for key, _ in METHODS], "periods": [key for key, _ in PERIODS], "records": len(rows)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Recomputed {len(rows)} records into {OUT}")


if __name__ == "__main__":
    main()
