"""Export the fixed and adaptive metrics to a traceable CSV table."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIELDS = [
    "strategy", "completed_vehicles", "mean_travel_time_s",
    "mean_waiting_time_s", "mean_time_loss_s", "mean_queue_vehicles",
    "simulation_seconds", "controller_gain", "random_seed",
]


def main() -> None:
    rows = []
    for mode in ("fixed", "adaptive"):
        data = json.loads((RESULTS / f"metrics_{mode}.json").read_text(encoding="utf-8"))
        rows.append({field: data.get(field, "") for field in FIELDS})
    output = RESULTS / "summary.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(output)


if __name__ == "__main__":
    main()
