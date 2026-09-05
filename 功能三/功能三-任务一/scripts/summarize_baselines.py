"""Create a stable, human-readable summary from a metrics.csv file."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

FIELDS = ("algorithm", "period", "steps", "total_demand", "throughput_est",
          "average_travel_time_s", "estimated_delay_s", "final_queue_proxy", "wall_seconds")

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("metrics", type=Path, nargs="?", default=Path("结果/baseline_runs/metrics.csv"))
    ap.add_argument("--output", type=Path, default=Path("结果/baseline_summary.csv"))
    args = ap.parse_args()
    with args.metrics.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r.get("period", ""), r.get("algorithm", "")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for row in rows: w.writerow({k: row.get(k, "") for k in FIELDS})
    print(json.dumps({"rows": len(rows), "output": str(args.output)}, ensure_ascii=False))

if __name__ == "__main__": main()
