"""Native Windows result window for a CityFlow trace; no browser required."""
from __future__ import annotations

import argparse
import csv
import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk


def latest_metric(path: Path, algorithm: str, period: str) -> dict[str, str]:
    if not path.exists(): return {}
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    return next((row for row in reversed(rows) if row["algorithm"] == algorithm and row["period"] == period), rows[-1] if rows else {})


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("trace", type=Path); ap.add_argument("--metrics", type=Path, default=Path("outputs/metrics.csv")); ap.add_argument("--summary", type=Path, default=None); args = ap.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"));
    if not trace: raise SystemExit("Trace is empty; no result window can be shown.")
    name = args.trace.stem.removeprefix("trace_")
    periods = ("morning", "midday", "evening")
    period = next((item for item in periods if name.endswith("_" + item)), "morning")
    algorithm = name[:-(len(period) + 1)] if name.endswith("_" + period) else name
    metric = latest_metric(args.metrics, algorithm, period); queue = [int(row["queue_proxy"]) for row in trace]
    root = tk.Tk(); root.title(f"雄安新区20路口 CityFlow - {algorithm} / {period}"); root.geometry("980x650"); root.minsize(760, 520)
    frame = ttk.Frame(root, padding=18); frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text="雄安新区 20 路口 CityFlow 仿真结果", font=("Microsoft YaHei", 18, "bold")).pack(anchor=tk.W)
    ttk.Label(frame, text=f"算法：{algorithm}    时段：{period}    决策记录：{len(trace)} 次", font=("Microsoft YaHei", 11)).pack(anchor=tk.W, pady=(6, 14))
    stats = ttk.Frame(frame); stats.pack(fill=tk.X)
    values = [("Travel time (s)", metric.get("average_travel_time_s", "-")), ("Delay (s)", metric.get("estimated_delay_s", "-")), ("Queue", metric.get("final_queue_proxy", "-")), ("Throughput", metric.get("throughput_est", "-")), ("Active vehicles", metric.get("final_active_vehicles", "-")), ("FRAP override", metric.get("frap_override_rate", "-"))]
    for label, value in values:
        box = ttk.LabelFrame(stats, text=label, padding=10); box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)); ttk.Label(box, text=value, font=("Consolas", 15, "bold")).pack()
    canvas = tk.Canvas(frame, bg="white", height=340, highlightthickness=1, highlightbackground="#aab7c4"); canvas.pack(fill=tk.BOTH, expand=True, pady=18)
    width, height, margin = 920, 340, 44; maximum = max(1, max(queue));
    canvas.create_line(margin, height-margin, width-margin, height-margin, fill="#708090"); canvas.create_line(margin, margin, margin, height-margin, fill="#708090")
    points = []
    for i, value in enumerate(queue):
        x = margin + (width - 2 * margin) * i / max(1, len(queue) - 1); y = height - margin - (height - 2 * margin) * value / maximum; points.extend((x, y))
    if len(points) >= 4: canvas.create_line(*points, fill="#007f5f", width=2, smooth=True)
    canvas.create_text(margin + 4, margin - 12, text=f"排队代理量（最大 {maximum}）", anchor=tk.W, fill="#28445b", font=("Microsoft YaHei", 10))
    canvas.create_text(width - margin, height - margin + 18, text="决策时刻", anchor=tk.E, fill="#28445b", font=("Microsoft YaHei", 10))
    ttk.Label(frame, text=f"轨迹文件：{args.trace}", foreground="#51606d").pack(anchor=tk.W)
    if args.summary and args.summary.exists():
        ttk.Label(frame, text="三时段汇总", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(8, 3))
        summary_box = ttk.Treeview(frame, columns=("period", "tt", "delay", "queue", "throughput"), show="headings", height=3)
        for col, title in (("period", "Period"), ("tt", "Travel time (s)"), ("delay", "Delay (s)"), ("queue", "Queue"), ("throughput", "Throughput")):
            summary_box.heading(col, text=title); summary_box.column(col, width=150, anchor=tk.CENTER)
        with args.summary.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle): summary_box.insert("", tk.END, values=(row.get("period", ""), row.get("average_travel_time_s", ""), row.get("estimated_delay_s", ""), row.get("final_queue_proxy", ""), row.get("throughput_est", "")))
        summary_box.pack(fill=tk.X, pady=(0, 6))
    ttk.Button(frame, text="关闭", command=root.destroy).pack(anchor=tk.E, pady=(10, 0))
    root.mainloop()


if __name__ == "__main__": main()
