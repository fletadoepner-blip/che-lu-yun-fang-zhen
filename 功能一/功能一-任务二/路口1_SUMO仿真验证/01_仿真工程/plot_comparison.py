"""Create publication-ready SUMO performance comparison figures."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch


PROJECT = Path(__file__).resolve().parent
RESULTS = PROJECT / "results"


def main() -> None:
    fixed = json.loads((RESULTS / "metrics_fixed.json").read_text(encoding="utf-8"))
    adaptive = json.loads((RESULTS / "metrics_adaptive.json").read_text(encoding="utf-8"))
    labels = ["平均旅行时间", "平均等待时间", "平均时间损失", "平均排队车辆数"]
    keys = ["mean_travel_time_s", "mean_waiting_time_s", "mean_time_loss_s", "mean_queue_vehicles"]
    units = ["s", "s", "s", "辆"]
    fixed_values = [fixed[key] for key in keys]
    adaptive_values = [adaptive[key] for key in keys]

    plt.rcParams.update({
        "font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 10,
        "axes.titleweight": "bold",
        "axes.labelcolor": "#243447",
        "xtick.color": "#243447",
        "ytick.color": "#243447",
    })
    figure, axes = plt.subplots(2, 2, figsize=(10.5, 6.6))
    figure.patch.set_facecolor("white")
    colors = ("#6E8FB8", "#E9784A")
    panel_ids = ("(a)", "(b)", "(c)", "(d)")

    for axis, panel, label, unit, baseline, proposal in zip(
        axes.flat, panel_ids, labels, units, fixed_values, adaptive_values
    ):
        positions = (-0.18, 0.18)
        bars = axis.bar(positions, (baseline, proposal), color=colors, width=0.10,
                        edgecolor="white", linewidth=0.8, zorder=3)
        upper_limit = max(max(baseline, proposal) * 1.25, 1.0)
        axis.set_ylim(0, upper_limit)
        axis.set_xlim(-0.50, 0.50)
        axis.set_xticks(positions, ("固定配时", "自适应控制"))
        axis.set_ylabel(unit)
        axis.set_title(f"{panel} {label}", loc="left", pad=8)
        axis.grid(axis="y", color="#D9E1E8", linewidth=0.8, zorder=0)
        axis.spines[["top", "right"]].set_visible(False)
        axis.spines[["left", "bottom"]].set_color("#8FA1B3")
        for bar, value in zip(bars, (baseline, proposal)):
            axis.text(bar.get_x() + bar.get_width() / 2, value + upper_limit * 0.025,
                      f"{value:.2f}", ha="center", va="bottom", fontsize=9, color="#243447")
        if baseline:
            change = (baseline - proposal) / baseline * 100
            improvement_text = f"改善 {change:.2f}%" if change >= 0 else f"劣化 {-change:.2f}%"
        else:
            improvement_text = "不可比较（基线为 0）"
        axis.text(0.5, upper_limit * 0.94, improvement_text, ha="center", va="top",
                  fontsize=9, color="#1D7A5A", fontweight="bold")

    figure.suptitle("deta-1 路口信号控制性能对比", fontsize=16, fontweight="bold", y=0.98)
    figure.legend(handles=[Patch(facecolor=colors[0], label="固定配时"),
                           Patch(facecolor=colors[1], label="自适应控制")],
                  loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.935))
    figure.text(0.5, 0.012, "注：改善率为固定配时相对自适应控制的降低比例。", ha="center", color="#5F6F7F", fontsize=9)
    figure.tight_layout(rect=(0.02, 0.05, 0.98, 0.89))
    output = RESULTS / "performance_comparison.png"
    figure.savefig(output, dpi=300, bbox_inches="tight")
    figure.savefig(RESULTS / "performance_comparison.pdf", bbox_inches="tight")
    print(output)
    # PyCharm may choose a non-interactive Agg backend. Open the saved image
    # through Windows so the visual result is still shown to the user.
    if sys.platform == "win32":
        try:
            os.startfile(output)
        except OSError:
            print("No default PNG viewer is configured; open the saved file manually.")
    elif "agg" not in plt.get_backend().lower():
        plt.show()


if __name__ == "__main__":
    main()
